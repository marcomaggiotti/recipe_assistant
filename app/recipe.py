"""Pizza dough recipe engine.

Turns a flour blend (baker's percentages) and an optional pre-ferment into a scaled
dough formula with per-ingredient weights and a fermentation schedule.

All percentages are "baker's percentages": expressed relative to total flour weight
(flour is always 100%). Flour blend percentages are relative to each other and are
normalized to sum to 100 before use.

A computed/saved recipe's flour blend lives under `ingredients.flours` (not a
top-level `flours` key). Its preferment - if any - is echoed back as a single
`pre_ferment` dict: `{"components": [{"name": ..., "percentage": ...}, ...],
"percentage": <baker's % of total flour>}`, or None when the recipe uses a plain
commercial-yeast dough. `components` names are purely descriptive/echoed metadata -
the engine always computes ONE aggregate preferment mass/formula regardless of how
many named components it lists (e.g. "biga 60% / poolish 40%"); it does not compute
each component separately.
"""
from __future__ import annotations

from typing import Any

# Generic baker's-percentage defaults, used whenever a caller doesn't override them.
# There's no named-style library anymore - these are just sane generic defaults.
DEFAULT_HYDRATION_PCT = 62.0
DEFAULT_SALT_PCT = 2.5
DEFAULT_OIL_PCT = 0.0
DEFAULT_BALL_WEIGHT_G = 250.0

_DIRECT_YEAST_PCT = 0.5  # commercial yeast baker's %, when there's no pre_ferment

_DEFAULT_PRE_FERMENT_PCT = 40.0  # % of total flour built into the preferment, unless overridden
_PRE_FERMENT_HYDRATION_PCT = 75.0  # simplified aggregate assumption, regardless of composition
_PRE_FERMENT_YEAST_PCT = 0.25  # of preferment flour weight; simplified aggregate assumption


def normalize_flours(flours: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    total = sum(f["percent"] for f in flours)
    warnings: list[str] = []
    if total <= 0:
        raise ValueError("flour percentages must sum to a positive number")
    if abs(total - 100.0) > 0.5:
        warnings.append(f"flour percentages summed to {total:.1f}%, normalized to 100%")
        factor = 100.0 / total
        flours = [{**f, "percent": round(f["percent"] * factor, 2)} for f in flours]
    return flours, warnings


def _leavening(
    pre_ferment: dict[str, Any] | None, flour_total_g: float, water_total_g: float,
    yeast_pct_override: float | None,
):
    if pre_ferment is None:
        yeast_pct = yeast_pct_override if yeast_pct_override is not None else _DIRECT_YEAST_PCT
        yeast_g = flour_total_g * yeast_pct / 100
        return {
            "type": "instant dry yeast",
            "grams": round(yeast_g, 2),
            "percent_of_flour": yeast_pct,
        }, []

    pct = pre_ferment["percentage"]
    preferment_flour_g = flour_total_g * pct / 100
    preferment_water_g = preferment_flour_g * _PRE_FERMENT_HYDRATION_PCT / 100
    preferment_yeast_g = preferment_flour_g * _PRE_FERMENT_YEAST_PCT / 100
    remaining_water_g = water_total_g - preferment_water_g
    warnings = []
    if remaining_water_g < 0:
        remaining_water_g = 0.0
        warnings.append(
            "hydration too low to cover the preferment's water at this percentage; "
            "remaining-dough water floored at 0g"
        )
    return {
        "type": "preferment",
        "components": pre_ferment["components"],
        "percent_of_flour": pct,
        "preferment_flour_g": round(preferment_flour_g, 1),
        "preferment_water_g": round(preferment_water_g, 1),
        "preferment_yeast_g": round(preferment_yeast_g, 2),
        "rest_hours": "12-20",
        "remaining_flour_g": round(flour_total_g - preferment_flour_g, 1),
        "remaining_water_g": round(remaining_water_g, 1),
        "note": "Aggregate preferment formula - components are descriptive only, not "
                "computed separately.",
    }, warnings


def _fermentation_schedule(has_pre_ferment: bool) -> list[dict[str, str]]:
    common_bake = {"stage": "Bake", "duration": "per oven", "temperature": "as hot as your oven allows",
                   "notes": "Stretch gently, preserving the rim's air bubbles."}

    if not has_pre_ferment:
        return [
            {"stage": "Mix", "duration": "10-15 min", "temperature": "room temp",
             "notes": "Combine flours, water, salt, yeast; mix to full gluten development."},
            {"stage": "Bulk ferment", "duration": "2 h", "temperature": "~22-24C room temp",
             "notes": "One fold at the 1h mark."},
            {"stage": "Ball & proof", "duration": "4-6 h", "temperature": "~22-24C room temp",
             "notes": "Divide into balls; proof covered until doubled and relaxed."},
            common_bake,
        ]
    return [
        {"stage": "Build preferment", "duration": "12-20 h", "temperature": "~18-20C cool room",
         "notes": "Ferment the preferment blend until bubbly/domed (wetter components) or "
                  "tripled and honeycombed (stiffer components)."},
        {"stage": "Final mix", "duration": "10-15 min", "temperature": "room temp",
         "notes": "Add the preferment to the remaining flour, water, salt (and oil); mix to "
                  "full gluten development."},
        {"stage": "Bulk ferment", "duration": "1-2 h", "temperature": "room temp",
         "notes": "Short bulk since the preferment already carried most of the fermentation."},
        {"stage": "Ball & proof", "duration": "3-6 h", "temperature": "room temp",
         "notes": "Proof until relaxed and pillowy."},
        common_bake,
    ]


def compute_recipe(
    *,
    flours: list[dict[str, Any]],
    pre_ferment: dict[str, Any] | None = None,
    hydration_pct: float | None = None,
    salt_pct: float | None = None,
    oil_pct: float | None = None,
    yeast_pct: float | None = None,
    ball_weight_g: float | None = None,
) -> dict[str, Any]:
    """Computes the dough formula for a SINGLE dough ball of `ball_weight_g` grams -
    this is the reusable "recipe", independent of how many balls you actually want to
    make. Use scale_recipe() to expand it into a batch of N balls.

    pre_ferment, when given, is a resolved dict `{"components": [{"name": ...,
    "percentage": ...}, ...], "percentage": <baker's % of total flour, defaults to 40
    when omitted by the caller>}`. Named components are echoed through as descriptive
    metadata only - the engine always computes one aggregate preferment formula, never
    per-component math.

    Any of hydration/salt/oil/yeast %  or ball weight left unset falls back to a
    generic baker's-percentage default (DEFAULT_* constants above).
    """
    flours_norm, warnings = normalize_flours(flours)

    hydration = hydration_pct if hydration_pct is not None else DEFAULT_HYDRATION_PCT
    salt = salt_pct if salt_pct is not None else DEFAULT_SALT_PCT
    oil = oil_pct if oil_pct is not None else DEFAULT_OIL_PCT
    ball_weight = ball_weight_g if ball_weight_g is not None else DEFAULT_BALL_WEIGHT_G

    # One ball's dough mass = flour + water + salt + oil (yeast/preferment mass reported
    # separately, since for preferment recipes it is drawn from the flour/water already
    # counted).
    parts = 1 + hydration / 100 + salt / 100 + oil / 100
    flour_total_g = ball_weight / parts
    water_total_g = flour_total_g * hydration / 100
    salt_g = flour_total_g * salt / 100
    oil_g = flour_total_g * oil / 100 if oil else 0.0

    leavening, leavening_warnings = _leavening(pre_ferment, flour_total_g, water_total_g, yeast_pct)
    warnings += leavening_warnings

    flours_out = [
        {**f, "grams": round(flour_total_g * f["percent"] / 100, 1)}
        for f in flours_norm
    ]

    pre_ferment_out = (
        {"components": pre_ferment["components"], "percentage": leavening["percent_of_flour"]}
        if pre_ferment is not None else None
    )

    ingredients_per_ball = {
        "flour_g": round(flour_total_g, 1),
        "water_g": round(water_total_g, 1),
        "salt_g": round(salt_g, 1),
        "oil_g": round(oil_g, 1),
    }

    return {
        "ingredients": {"flours": flours_out},
        "pre_ferment": pre_ferment_out,
        "hydration_pct": hydration,
        "salt_pct": salt,
        "oil_pct": oil,
        "leavening": leavening,
        "ball_weight_g": ball_weight,
        "ingredients_per_ball": ingredients_per_ball,
        "fermentation_schedule": _fermentation_schedule(pre_ferment is not None),
        "warnings": warnings,
    }


# leavening dict keys that hold gram quantities and need scaling with batch size (the
# rest - "type", "components", "rest_hours", "percent_of_flour", "note" - are
# ratios/text/metadata, unaffected).
_LEAVENING_GRAM_KEYS = (
    "grams", "preferment_flour_g", "preferment_water_g", "preferment_yeast_g",
    "remaining_flour_g", "remaining_water_g",
)


def scale_recipe(recipe: dict[str, Any], num_balls: int) -> dict[str, Any]:
    """Expands a single-ball recipe (as returned by compute_recipe(), or a saved
    recipe fetched from a PizzaRepository - both are per-one-ball formulas) into a
    batch of `num_balls` balls. Percentages, pre_ferment composition, and the
    fermentation schedule don't change with batch size; ingredients_per_ball is left
    untouched too, so it stays a stable per-ball reference regardless of num_balls.
    """
    if num_balls < 1:
        raise ValueError("num_balls must be at least 1")
    scaled = dict(recipe)
    scaled["num_balls"] = num_balls
    scaled["total_dough_g"] = round(recipe["ball_weight_g"] * num_balls, 1)
    scaled["ingredients"] = {
        "flours": [{**f, "grams": round(f["grams"] * num_balls, 1)} for f in recipe["ingredients"]["flours"]]
    }
    scaled["leavening"] = {
        k: (round(v * num_balls, 2) if k in _LEAVENING_GRAM_KEYS else v)
        for k, v in recipe["leavening"].items()
    }
    scaled["ingredients_total"] = {k: round(v * num_balls, 1) for k, v in recipe["ingredients_per_ball"].items()}
    return scaled
