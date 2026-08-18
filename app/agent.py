"""Thin LLM agent layer: lets a natural-language instruction drive the service's own
recipe generation/storage through Anthropic tool-calling, instead of hand-written REST calls.
"""
import json
from typing import Any

from .config import Settings
from .db import PizzaRepository
from .flours import FlourCatalogStore
from .recipe import PREFERMENT_TECHNIQUES, STYLE_LIBRARY, TECHNIQUES
from .recipe import compute_recipe as _compute_recipe
from .recipe import scale_recipe
from .styles import StyleStore

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
_PRE_FERMENTS_SCHEMA = {
    "type": "array",
    "maxItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": list(PREFERMENT_TECHNIQUES)},
            "percentage": {"type": "number", "description": "Baker's % of total flour built into this preferment/starter. Defaults to 40 for poolish/biga, 20 for sourdough, if this entry is omitted entirely."},
        },
        "required": ["type", "percentage"],
    },
    "description": (
        "At most one - only one preferment technique can be active per recipe. Its "
        "`type` becomes the recipe's technique unless `technique` is also given "
        "explicitly (must then match). Omit entirely for direct/same_day/cold_ferment_* "
        "techniques, which don't build a separate preferment."
    ),
}

TOOLS = [
    {
        "name": "generate_pizza_recipe",
        "description": (
            "Compute a pizza dough recipe from a flour blend (baker's percentages that "
            "don't need to sum to exactly 100 - they get normalized), a fermentation "
            "technique, and an optional named style anchored to a real pizza-chef/cookbook "
            "reference. Every ingredients.flours[].pizza_flours_id must match an entry in the "
            "flour catalogue (list_pizza_flours) - its id or one of its localized names/codes "
            "(e.g. '00', 'Farina 00', 'Weizenmehl 405', 'T45' all resolve to the same flour); "
            "unrecognized flour names are rejected. ingredients.flours[]['ash%'] is optional and "
            "only meaningful for milled wheat flours (e.g. 0.55 for Italian Tipo 00) - it's "
            "cross-checked against the resolved flour's ash range and helps disambiguate. "
            "ingredients.flours[].description is an optional free-text brand/product note (e.g. "
            "'Semola Caputo') - purely informational, not matched against the catalogue. Any of "
            "hydration/salt/oil/yeast % or ball weight left unset falls back to the chosen "
            "style's defaults ('custom' style = generic defaults with no attribution). "
            "pre_ferments (at most one entry) sets a poolish/biga/sourdough preferment and its "
            "baker's % of total flour - its type becomes the technique if technique is left "
            "unset; omit both for a plain 'direct' dough, or set technique alone for "
            "same_day/cold_ferment_24h/48h/72h (no separate preferment). The formula is always "
            "for a single dough ball; pass num_balls to scale ingredient quantities up to a "
            "batch of that many balls (defaults to 1)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredients": _INGREDIENTS_SCHEMA,
                "pre_ferments": _PRE_FERMENTS_SCHEMA,
                "technique": {"type": "string", "enum": TECHNIQUES, "description": "Optional when pre_ferments has an entry (inferred from its type); defaults to 'direct' otherwise."},
                "style": {"type": "string", "enum": list(STYLE_LIBRARY), "default": "custom"},
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
                "pre_ferments": _PRE_FERMENTS_SCHEMA,
                "technique": {"type": "string", "enum": TECHNIQUES, "description": "Optional when pre_ferments has an entry (inferred from its type); defaults to 'direct' otherwise."},
                "style": {"type": "string", "enum": list(STYLE_LIBRARY), "default": "custom"},
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
        "name": "list_pizza_styles",
        "description": "List the built-in named styles, each with its pizza-chef/cookbook attribution and defaults.",
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
    "turns a flour blend, a fermentation technique, and an optional named pizza-chef/"
    "cookbook style into a scaled dough recipe (ingredient weights + fermentation "
    "schedule), and can save/list/fetch/delete recipes. Use the provided tools rather than "
    "computing the math yourself. Be concise, and mention the style's book/author "
    "attribution when one applies."
)


def _resolve_technique(tool_input: dict[str, Any]) -> tuple[str, float | None]:
    """Mirrors RecipeGenerateRequest._resolve_technique in schemas.py: pre_ferments[0].type
    becomes the technique unless an explicit (matching) technique is also given; defaults
    to 'direct' when neither is set. Returns (technique, pre_ferment_percentage)."""
    pre_ferments = tool_input.get("pre_ferments") or []
    if len(pre_ferments) > 1:
        raise ValueError("only one pre_ferment is currently supported")
    technique = tool_input.get("technique")
    if pre_ferments:
        inferred = pre_ferments[0]["type"]
        if technique is not None and technique != inferred:
            raise ValueError(f"technique '{technique}' does not match pre_ferments[0].type '{inferred}'")
        return inferred, pre_ferments[0].get("percentage")
    return technique or "direct", None


def _generate(style_store: StyleStore, flour_store: FlourCatalogStore, tool_input: dict[str, Any]) -> dict[str, Any]:
    style = tool_input.get("style", "custom")
    style_defaults = style_store.get(style)
    if style_defaults is None:
        raise ValueError(f"unknown style '{style}'")

    flours = tool_input["ingredients"]["flours"]
    unknown = [
        f["pizza_flours_id"] for f in flours
        if flour_store.resolve(f["pizza_flours_id"], f.get("ash%")) is None
    ]
    if unknown:
        raise ValueError(f"unknown flour type(s): {', '.join(unknown)} - see list_pizza_flours for the allowed catalogue")

    technique, pre_ferment_percentage = _resolve_technique(tool_input)

    return _compute_recipe(
        flours=flours,
        technique=technique,
        style=style,
        style_defaults=style_defaults,
        hydration_pct=tool_input.get("hydration_pct"),
        salt_pct=tool_input.get("salt_pct"),
        oil_pct=tool_input.get("oil_pct"),
        yeast_pct=tool_input.get("yeast_pct"),
        ball_weight_g=tool_input.get("ball_weight_g"),
        pre_ferment_percentage=pre_ferment_percentage,
    )


def _dispatch(
    repo: PizzaRepository, style_store: StyleStore, flour_store: FlourCatalogStore,
    name: str, tool_input: dict[str, Any],
) -> Any:
    try:
        if name == "generate_pizza_recipe":
            base = _generate(style_store, flour_store, tool_input)
            return scale_recipe(base, tool_input.get("num_balls", 1))
        if name == "save_pizza_recipe":
            base = _generate(style_store, flour_store, tool_input)
            return repo.create(tool_input["name"], base)
        if name == "list_pizza_styles":
            return {
                "styles": [
                    {"key": k, "label": s["label"], "author": s["author"], "book": s["book"],
                     "technique": s["technique"], "notes": s["notes"]}
                    for k, s in style_store.list().items()
                ]
            }
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
    settings: Settings, repo: PizzaRepository, style_store: StyleStore, flour_store: FlourCatalogStore,
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
            result = _dispatch(repo, style_store, flour_store, block.name, block.input)
            tool_calls.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})

    return "Reached max tool-call iterations without a final answer.", tool_calls
