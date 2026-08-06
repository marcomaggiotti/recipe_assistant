"""Thin LLM agent layer: lets a natural-language instruction drive the service's own
recipe generation/storage through Anthropic tool-calling, instead of hand-written REST calls.
"""
import json
from typing import Any

from .config import Settings
from .db import PizzaRepository
from .recipe import STYLE_LIBRARY, TECHNIQUES
from .recipe import compute_recipe as _compute_recipe

TOOLS = [
    {
        "name": "generate_pizza_recipe",
        "description": (
            "Compute a scaled pizza dough recipe from a flour blend (baker's percentages "
            "that don't need to sum to exactly 100 - they get normalized), a fermentation "
            "technique, and an optional named style anchored to a real pizza-chef/cookbook "
            "reference. Any of hydration/salt/oil/yeast %, ball weight, or number of balls "
            "left unset falls back to the chosen style's defaults ('custom' style = generic "
            "defaults with no attribution)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "flours": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"type": {"type": "string"}, "percent": {"type": "number"}},
                        "required": ["type", "percent"],
                    },
                },
                "technique": {"type": "string", "enum": TECHNIQUES},
                "style": {"type": "string", "enum": list(STYLE_LIBRARY), "default": "custom"},
                "hydration_pct": {"type": "number"},
                "salt_pct": {"type": "number"},
                "oil_pct": {"type": "number"},
                "yeast_pct": {"type": "number"},
                "num_balls": {"type": "integer", "default": 4},
                "ball_weight_g": {"type": "number"},
            },
            "required": ["flours", "technique"],
        },
    },
    {
        "name": "save_pizza_recipe",
        "description": "Save a previously generated recipe result (or generate-and-save in one step) under a name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "flours": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"type": {"type": "string"}, "percent": {"type": "number"}},
                        "required": ["type", "percent"],
                    },
                },
                "technique": {"type": "string", "enum": TECHNIQUES},
                "style": {"type": "string", "enum": list(STYLE_LIBRARY), "default": "custom"},
                "hydration_pct": {"type": "number"},
                "salt_pct": {"type": "number"},
                "oil_pct": {"type": "number"},
                "yeast_pct": {"type": "number"},
                "num_balls": {"type": "integer", "default": 4},
                "ball_weight_g": {"type": "number"},
            },
            "required": ["name", "flours", "technique"],
        },
    },
    {
        "name": "list_pizza_styles",
        "description": "List the built-in named styles, each with its pizza-chef/cookbook attribution and defaults.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_pizza_recipes",
        "description": "List saved pizza recipes.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}, "offset": {"type": "integer", "default": 0}},
        },
    },
    {
        "name": "get_pizza_recipe",
        "description": "Get a saved pizza recipe by id.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
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


def _generate(tool_input: dict[str, Any]) -> dict[str, Any]:
    return _compute_recipe(
        flours=tool_input["flours"],
        technique=tool_input["technique"],
        style=tool_input.get("style", "custom"),
        hydration_pct=tool_input.get("hydration_pct"),
        salt_pct=tool_input.get("salt_pct"),
        oil_pct=tool_input.get("oil_pct"),
        yeast_pct=tool_input.get("yeast_pct"),
        num_balls=tool_input.get("num_balls", 4),
        ball_weight_g=tool_input.get("ball_weight_g"),
    )


def _dispatch(repo: PizzaRepository, name: str, tool_input: dict[str, Any]) -> Any:
    try:
        if name == "generate_pizza_recipe":
            return _generate(tool_input)
        if name == "save_pizza_recipe":
            result = _generate(tool_input)
            return repo.create(tool_input["name"], result)
        if name == "list_pizza_styles":
            return {
                "styles": [
                    {"key": k, "label": s["label"], "author": s["author"], "book": s["book"],
                     "technique": s["technique"], "notes": s["notes"]}
                    for k, s in STYLE_LIBRARY.items()
                ]
            }
        if name == "list_pizza_recipes":
            items, total = repo.list(tool_input.get("limit", 20), tool_input.get("offset", 0))
            return {"items": items, "count": total}
        if name == "get_pizza_recipe":
            record = repo.get(tool_input["id"])
            return record if record else {"error": "not found"}
        if name == "delete_pizza_recipe":
            return {"deleted": repo.delete(tool_input["id"])}
    except ValueError as exc:
        return {"error": str(exc)}
    return {"error": f"unknown tool {name}"}


def run_agent(settings: Settings, repo: PizzaRepository, message: str, history: list[dict]) -> tuple[str, list[dict]]:
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
            result = _dispatch(repo, block.name, block.input)
            tool_calls.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})

    return "Reached max tool-call iterations without a final answer.", tool_calls
