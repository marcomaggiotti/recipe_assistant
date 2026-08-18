"""Thin LLM agent layer: lets a natural-language instruction drive the service's own
recipe generation/storage through Anthropic tool-calling, instead of hand-written REST calls.
"""
import json
from typing import Any

from .config import Settings
from .db import PizzaRepository
from .flours import FlourCatalogStore
from .pre_ferments import PreFermentTypeStore
from .recipe import compute_recipe as _compute_recipe
from .recipe import scale_recipe

# Shared by generate_pizza_recipe/save_pizza_recipe below.
_INGREDIENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "flours": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pizza_flours_id": {"type": "string"},
                    "ash%": {"type": "number", "description": "Ash content %, e.g. 0.55 for Italian Tipo 00"},
                    "description": {"type": "string", "description": "Optional brand/product note, e.g. 'Semola Caputo'"},
                    "percent": {"type": "number"},
                },
                "required": ["pizza_flours_id", "percent"],
            },
        },
    },
    "required": ["flours"],
}
_PRE_FERMENT_SCHEMA = {
    "type": "object",
    "description": (
        "Omit entirely for a plain commercial-yeast dough. Set to build a preferment - "
        "either inline named components (e.g. biga 60% / poolish 40%) or a type_id "
        "reference to a saved blend from list_pre_ferment_types. The engine always "
        "computes ONE aggregate preferment formula; named components are descriptive "
        "only, never computed separately."
    ),
    "properties": {
        "type_id": {"type": "string", "description": "References a saved blend instead of describing components inline. Set this or `components`, not both."},
        "components": {
            "type": "array",
            "description": "Inline named components, e.g. [{'name': 'biga', 'percentage': 60}, {'name': 'poolish', 'percentage': 40}] - percentages must sum to 100. Set this or `type_id`, not both.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "e.g. 'biga', 'sourdough', 'poolish'"},
                    "percentage": {"type": "number", "description": "This component's share of the preferment mix itself, not of total dough flour"},
                },
                "required": ["name", "percentage"],
            },
        },
        "percentage": {"type": "number", "description": "Baker's % of total flour built into the preferment. Defaults to 40 if omitted."},
    },
}

TOOLS = [
    {
        "name": "generate_pizza_recipe",
        "description": (
            "Compute a pizza dough recipe from a flour blend (baker's percentages that "
            "don't need to sum to exactly 100 - they get normalized) and an optional "
            "pre-ferment. Every ingredients.flours[].pizza_flours_id must match an entry in the "
            "flour catalogue (list_pizza_flours) - its id or one of its localized names/codes "
            "(e.g. '00', 'Farina 00', 'Weizenmehl 405', 'T45' all resolve to the same flour); "
            "unrecognized flour names are rejected. ingredients.flours[]['ash%'] is optional and "
            "only meaningful for milled wheat flours (e.g. 0.55 for Italian Tipo 00) - it's "
            "cross-checked against the resolved flour's ash range and helps disambiguate. "
            "ingredients.flours[].description is an optional free-text brand/product note (e.g. "
            "'Semola Caputo') - purely informational, not matched against the catalogue. Any of "
            "hydration/salt/oil/yeast % or ball weight left unset falls back to a generic "
            "baker's-percentage default. pre_ferment (optional) builds a preferment - see its "
            "schema for the type_id vs inline-components choice. The formula is always for a "
            "single dough ball; pass num_balls to scale ingredient quantities up to a batch of "
            "that many balls (defaults to 1)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredients": _INGREDIENTS_SCHEMA,
                "pre_ferment": _PRE_FERMENT_SCHEMA,
                "hydration_pct": {"type": "number"},
                "salt_pct": {"type": "number"},
                "oil_pct": {"type": "number"},
                "yeast_pct": {"type": "number"},
                "ball_weight_g": {"type": "number"},
                "num_balls": {"type": "integer", "default": 1, "description": "Batch size to scale the formula to"},
            },
            "required": ["ingredients"],
        },
    },
    {
        "name": "save_pizza_recipe",
        "description": (
            "Save a single-ball dough formula (generate-and-save in one step) under a name. "
            "Always saves one ball's worth - use num_balls on get_pizza_recipe later to "
            "scale it to a batch when it's actually time to bake."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "ingredients": _INGREDIENTS_SCHEMA,
                "pre_ferment": _PRE_FERMENT_SCHEMA,
                "hydration_pct": {"type": "number"},
                "salt_pct": {"type": "number"},
                "oil_pct": {"type": "number"},
                "yeast_pct": {"type": "number"},
                "ball_weight_g": {"type": "number"},
            },
            "required": ["name", "ingredients"],
        },
    },
    {
        "name": "list_pre_ferment_types",
        "description": "List the saved pre-ferment type blends (id + named components) a recipe's pre_ferment.type_id can reference.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_pizza_flours",
        "description": (
            "List the international flour catalogue. Every ingredients.flours[].pizza_flours_id on "
            "generate_pizza_recipe/save_pizza_recipe must match one of these entries' id "
            "or one of its localized names/codes (names differ by country). Entries for milled "
            "wheat refinement grades also carry ash_min_pct/ash_max_pct."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_pizza_recipes",
        "description": "List saved pizza recipes (each as a single-ball formula).",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}, "offset": {"type": "integer", "default": 0}},
        },
    },
    {
        "name": "get_pizza_recipe",
        "description": "Get a saved pizza recipe by id, scaled to num_balls balls (defaults to 1).",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "num_balls": {"type": "integer", "default": 1, "description": "Batch size to scale the formula to"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_pizza_recipe",
        "description": "Delete a saved pizza recipe by id.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
]

SYSTEM_PROMPT = (
    "You are the pizza-service agent, a small AI agent embedded in a microservice that "
    "turns a flour blend and an optional pre-ferment (poolish, biga, sourdough, or a "
    "custom named combination) into a scaled dough recipe (ingredient weights + "
    "fermentation schedule), and can save/list/fetch/delete recipes. Use the provided "
    "tools rather than computing the math yourself. Be concise."
)


def _resolve_pre_ferment(pre_ferment_store: PreFermentTypeStore, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Mirrors routers/pizza.py's _resolve_pre_ferment: turns the tool call's pre_ferment
    (inline components, or a type_id reference) into the {"components": [...],
    "percentage": ...} shape compute_recipe() expects."""
    pre_ferment = tool_input.get("pre_ferment")
    if not pre_ferment:
        return None
    type_id = pre_ferment.get("type_id")
    components = pre_ferment.get("components")
    if bool(type_id) == bool(components):
        raise ValueError("set exactly one of pre_ferment.type_id or pre_ferment.components")
    if type_id is not None:
        saved = pre_ferment_store.get(type_id)
        if saved is None:
            raise ValueError(f"unknown pre_ferment type_id '{type_id}'")
        components = saved["preferments"]
    else:
        total = sum(c["percentage"] for c in components)
        if abs(total - 100.0) > 0.5:
            raise ValueError(f"pre_ferment.components percentages must sum to 100 (got {total:.1f})")
    return {"components": components, "percentage": pre_ferment.get("percentage", 40.0)}


def _generate(pre_ferment_store: PreFermentTypeStore, flour_store: FlourCatalogStore, tool_input: dict[str, Any]) -> dict[str, Any]:
    flours = tool_input["ingredients"]["flours"]
    unknown = [
        f["pizza_flours_id"] for f in flours
        if flour_store.resolve(f["pizza_flours_id"], f.get("ash%")) is None
    ]
    if unknown:
        raise ValueError(f"unknown flour type(s): {', '.join(unknown)} - see list_pizza_flours for the allowed catalogue")

    pre_ferment = _resolve_pre_ferment(pre_ferment_store, tool_input)

    return _compute_recipe(
        flours=flours,
        pre_ferment=pre_ferment,
        hydration_pct=tool_input.get("hydration_pct"),
        salt_pct=tool_input.get("salt_pct"),
        oil_pct=tool_input.get("oil_pct"),
        yeast_pct=tool_input.get("yeast_pct"),
        ball_weight_g=tool_input.get("ball_weight_g"),
    )


def _dispatch(
    repo: PizzaRepository, pre_ferment_store: PreFermentTypeStore, flour_store: FlourCatalogStore,
    name: str, tool_input: dict[str, Any],
) -> Any:
    try:
        if name == "generate_pizza_recipe":
            base = _generate(pre_ferment_store, flour_store, tool_input)
            return scale_recipe(base, tool_input.get("num_balls", 1))
        if name == "save_pizza_recipe":
            base = _generate(pre_ferment_store, flour_store, tool_input)
            return repo.create(tool_input["name"], base)
        if name == "list_pre_ferment_types":
            return {"items": pre_ferment_store.list()}
        if name == "list_pizza_flours":
            return {"flours": flour_store.list()}
        if name == "list_pizza_recipes":
            items, total = repo.list(tool_input.get("limit", 20), tool_input.get("offset", 0))
            return {"items": items, "count": total}
        if name == "get_pizza_recipe":
            record = repo.get(tool_input["id"])
            if not record:
                return {"error": "not found"}
            return scale_recipe(record, tool_input.get("num_balls", 1))
        if name == "delete_pizza_recipe":
            return {"deleted": repo.delete(tool_input["id"])}
    except ValueError as exc:
        return {"error": str(exc)}
    return {"error": f"unknown tool {name}"}


def run_agent(
    settings: Settings, repo: PizzaRepository, pre_ferment_store: PreFermentTypeStore, flour_store: FlourCatalogStore,
    message: str, history: list[dict],
) -> tuple[str, list[dict]]:
    if not settings.anthropic_api_key:
        return (
            "Agent chat requires ANTHROPIC_API_KEY to be configured on this service.",
            [],
        )

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    messages = list(history) + [{"role": "user", "content": message}]
    tool_calls: list[dict] = []

    for _ in range(5):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            return text, tool_calls

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _dispatch(repo, pre_ferment_store, flour_store, block.name, block.input)
            tool_calls.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})

    return "Reached max tool-call iterations without a final answer.", tool_calls
