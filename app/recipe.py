"""Pizza dough recipe engine.

Turns a flour blend (baker's percentages), a fermentation technique, and an optional
named style (each style is anchored to a real pizza-chef/cookbook reference) into a
scaled dough formula with per-ingredient weights and a fermentation schedule.

All percentages are "baker's percentages": expressed relative to total flour weight
(flour is always 100%). Flour blend percentages are relative to each other and are
normalized to sum to 100 before use.
"""
from __future__ import annotations

from typing import Any

TECHNIQUES = [
    "direct",
    "same_day",
    "poolish",
    "biga",
    "sourdough",
    "cold_ferment_24h",
    "cold_ferment_48h",
    "cold_ferment_72h",
]

# Each entry anchors the style's defaults to a real pizza-chef or cookbook reference,
# so a generated recipe can cite "the type of book/author" it follows. "custom" is the
# no-attribution fallback used when the caller just wants a generic formula.
STYLE_LIBRARY: dict[str, dict[str, Any]] = {
    "neapolitan_avpn": {
        "label": "Neapolitan (Verace Pizza Napoletana)",
        "author": "Associazione Verace Pizza Napoletana (AVPN)",
        "book": "AVPN Disciplinare (official production standard)",
        "hydration_pct": 60.0, "salt_pct": 2.8, "oil_pct": 0.0,
        "technique": "direct", "ball_weight_g": 250.0,
        "suggested_flours": ["Italian 00 flour"],
        "notes": "Soft, high-protein 00 flour; short room-temperature ferment; "
                 "cooked ~60-90s at 430-480C in a wood-fired oven.",
    },
    "ny_style": {
        "label": "New York style",
        "author": "Tony Gemignani",
        "book": "The Pizza Bible",
        "hydration_pct": 63.0, "salt_pct": 2.5, "oil_pct": 3.0,
        "technique": "cold_ferment_48h", "ball_weight_g": 300.0,
        "suggested_flours": ["High-gluten bread flour"],
        "notes": "Large, foldable, oil-enriched slices; baked on a deck at ~290-320C.",
    },
    "detroit_style": {
        "label": "Detroit style (pan pizza)",
        "author": "Ken Forkish",
        "book": "The Elements of Pizza",
        "hydration_pct": 75.0, "salt_pct": 2.2, "oil_pct": 2.0,
        "technique": "poolish", "ball_weight_g": 450.0,
        "suggested_flours": ["Bread flour"],
        "notes": "Wet dough proofed directly in an oiled steel pan; brick cheese to "
                 "the edges for the caramelized 'frico' crust.",
    },
    "roman_al_taglio": {
        "label": "Roman-style al taglio",
        "author": "Gabriele Bonci",
        "book": "Pizza: Seasonal Recipes from Rome's Legendary Pizzarium",
        "hydration_pct": 85.0, "salt_pct": 2.5, "oil_pct": 4.0,
        "technique": "biga", "ball_weight_g": 700.0,
        "suggested_flours": ["Strong bread flour", "Whole wheat (small %)"],
        "notes": "Very wet, biga-based dough baked in trays and sold by the cut.",
    },
    "sourdough_fwsy": {
        "label": "Naturally leavened, country-style",
        "author": "Ken Forkish",
        "book": "Flour Water Salt Yeast",
        "hydration_pct": 68.0, "salt_pct": 2.5, "oil_pct": 1.0,
        "technique": "sourdough", "ball_weight_g": 260.0,
        "suggested_flours": ["Bread flour", "Whole wheat (small %)"],
        "notes": "Levain-based dough with a long cold retard for flavor development.",
    },
    "american_pie_reinhart": {
        "label": "American artisan pizza",
        "author": "Peter Reinhart",
        "book": "American Pie: My Search for the Perfect Pizza",
        "hydration_pct": 65.0, "salt_pct": 2.0, "oil_pct": 2.0,
        "technique": "poolish", "ball_weight_g": 270.0,
        "suggested_flours": ["Bread flour", "Italian 00 flour"],
        "notes": "Preferment-driven formula designed for home ovens.",
    },
    "modernist_pizza": {
        "label": "Precision baker's-percentage formula",
        "author": "Nathan Myhrvold et al. (Modernist Cuisine)",
        "book": "Modernist Pizza",
        "hydration_pct": 65.0, "salt_pct": 2.5, "oil_pct": 0.0,
        "technique": "cold_ferment_72h", "ball_weight_g": 250.0,
        "suggested_flours": ["Italian 00 flour", "Bread flour"],
        "notes": "Long, cold, methodical fermentation for maximum flavor and consistency.",
    },
    "custom": {
        "label": "Custom formulation",
        "author": None,
        "book": None,
        "hydration_pct": 62.0, "salt_pct": 2.5, "oil_pct": 0.0,
        "technique": "direct", "ball_weight_g": 250.0,
        "suggested_flours": [],
        "notes": "No specific chef/book attribution - generic baker's-percentage "
                 "defaults, override any of them freely.",
    },
}

# Commercial-yeast baker's % (of flour weight) by ferment length, for techniques that
# don't build a separate preferment.
_DIRECT_YEAST_PCT = {
    "direct": 0.5,
    "same_day": 1.2,
    "cold_ferment_24h": 0.3,
    "cold_ferment_48h": 0.15,
    "cold_ferment_72h": 0.08,
}

_POOLISH_FLOUR_PCT = 40.0  # % of total flour built into a poolish, unless overridden
_BIGA_FLOUR_PCT = 40.0  # % of total flour built into a biga, unless overridden
_SOURDOUGH_STARTER_PCT = 20.0  # % of total flour, as mature 100%-hydration starter, unless overridden


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
    technique: str, flour_total_g: float, water_total_g: float, yeast_pct_override: float | None,
    poolish_pct_override: float | None = None,
    biga_pct_override: float | None = None,
    sourdough_pct_override: float | None = None,
):
    if technique in ("poolish", "biga"):
        default_pct = _POOLISH_FLOUR_PCT if technique == "poolish" else _BIGA_FLOUR_PCT
        override_pct = poolish_pct_override if technique == "poolish" else biga_pct_override
        preferment_pct = override_pct if override_pct is not None else default_pct
        preferment_flour_g = flour_total_g * preferment_pct / 100
        preferment_hydration = 100.0 if technique == "poolish" else 50.0
        preferment_water_g = preferment_flour_g * preferment_hydration / 100
        preferment_yeast_pct = 0.2 if technique == "poolish" else 0.3
        preferment_yeast_g = preferment_flour_g * preferment_yeast_pct / 100
        remaining_water_g = water_total_g - preferment_water_g
        warnings = []
        if remaining_water_g < 0:
            remaining_water_g = 0.0
            warnings.append(
                "hydration too low to cover the preferment's water at this technique's "
                "preferment size; remaining-dough water floored at 0g"
            )
        return {
            "type": technique,
            "percent_of_flour": preferment_pct,
            "preferment_flour_g": round(preferment_flour_g, 1),
            "preferment_water_g": round(preferment_water_g, 1),
            "preferment_yeast_g": round(preferment_yeast_g, 2),
            "rest_hours": "12-16" if technique == "poolish" else "16-20",
            "remaining_flour_g": round(flour_total_g - preferment_flour_g, 1),
            "remaining_water_g": round(remaining_water_g, 1),
        }, warnings

    if technique == "sourdough":
        starter_pct = sourdough_pct_override if sourdough_pct_override is not None else _SOURDOUGH_STARTER_PCT
        starter_g = flour_total_g * starter_pct / 100
        return {
            "type": "mature sourdough starter (100% hydration)",
            "grams": round(starter_g, 1),
            "percent_of_flour": starter_pct,
            "note": "Simplified formula: starter mass is listed separately rather than "
                    "deducted from the flour/water totals above.",
        }, []

    yeast_pct = yeast_pct_override if yeast_pct_override is not None else _DIRECT_YEAST_PCT[technique]
    yeast_g = flour_total_g * yeast_pct / 100
    return {
        "type": "instant dry yeast",
        "grams": round(yeast_g, 2),
        "percent_of_flour": yeast_pct,
    }, []


def _fermentation_schedule(technique: str) -> list[dict[str, str]]:
    common_bake = {"stage": "Bake", "duration": "per oven", "temperature": "as hot as your oven allows",
                   "notes": "Stretch gently, preserving the rim's air bubbles."}

    if technique == "direct":
        return [
            {"stage": "Mix", "duration": "10-15 min", "temperature": "room temp",
             "notes": "Combine flours, water, salt, yeast; mix to full gluten development."},
            {"stage": "Bulk ferment", "duration": "2 h", "temperature": "~22-24C room temp",
             "notes": "One fold at the 1h mark."},
            {"stage": "Ball & proof", "duration": "4-6 h", "temperature": "~22-24C room temp",
             "notes": "Divide into balls; proof covered until doubled and relaxed."},
            common_bake,
        ]
    if technique == "same_day":
        return [
            {"stage": "Mix", "duration": "10-15 min", "temperature": "room temp",
             "notes": "Combine flours, water, salt, yeast; mix to full gluten development."},
            {"stage": "Short bulk ferment", "duration": "45-60 min", "temperature": "~24-26C room temp",
             "notes": "Warmer/shorter than a direct dough since it must be ready same-day."},
            {"stage": "Ball & proof", "duration": "2-3 h", "temperature": "~24-26C room temp",
             "notes": "Divide into balls; proof covered until puffy."},
            common_bake,
        ]
    if technique == "poolish":
        return [
            {"stage": "Build poolish", "duration": "12-16 h", "temperature": "~20C room temp",
             "notes": "Equal parts (by weight) reserved flour and water, pinch of yeast; "
                      "ferment until bubbly and domed."},
            {"stage": "Final mix", "duration": "10-15 min", "temperature": "room temp",
             "notes": "Add poolish to remaining flour, water, salt (and oil); mix to full development."},
            {"stage": "Bulk ferment", "duration": "1-2 h", "temperature": "room temp",
             "notes": "Short bulk since the poolish already carried most of the fermentation."},
            {"stage": "Ball & proof", "duration": "4-6 h", "temperature": "room temp",
             "notes": "Proof until relaxed and pillowy."},
            common_bake,
        ]
    if technique == "biga":
        return [
            {"stage": "Build biga", "duration": "16-20 h", "temperature": "~18C cool room",
             "notes": "Stiff, low-hydration preferment; ferment until tripled and honeycombed."},
            {"stage": "Final mix", "duration": "10-15 min", "temperature": "room temp",
             "notes": "Break up the biga into the remaining flour, water, salt (and oil)."},
            {"stage": "Bulk ferment", "duration": "1 h", "temperature": "room temp", "notes": ""},
            {"stage": "Ball & proof", "duration": "3-5 h", "temperature": "room temp",
             "notes": "Proof until relaxed; biga doughs are often baked at high hydration in trays."},
            common_bake,
        ]
    if technique == "sourdough":
        return [
            {"stage": "Build/refresh levain", "duration": "6-8 h", "temperature": "~24-26C room temp",
             "notes": "Starter should double and be at peak activity before mixing."},
            {"stage": "Mix", "duration": "10-15 min", "temperature": "room temp",
             "notes": "Combine flours, water, salt, active levain."},
            {"stage": "Bulk ferment with folds", "duration": "3-4 h", "temperature": "~24-26C room temp",
             "notes": "3-4 sets of stretch-and-folds in the first 2h."},
            {"stage": "Ball & cold retard", "duration": "24-72 h", "temperature": "~3-4C refrigerated",
             "notes": "Divide into balls; slow, cold fermentation develops flavor."},
            {"stage": "Temper", "duration": "2 h", "temperature": "room temp",
             "notes": "Bring balls back to room temperature before shaping."},
            common_bake,
        ]
    # cold_ferment_24h / 48h / 72h
    hours = technique.split("_")[-1].replace("h", "")
    return [
        {"stage": "Mix", "duration": "10-15 min", "temperature": "room temp",
         "notes": "Combine flours, water, salt, yeast; mix to full gluten development."},
        {"stage": "Short bulk ferment", "duration": "30-60 min", "temperature": "room temp", "notes": ""},
        {"stage": "Ball & cold retard", "duration": f"{hours} h", "temperature": "~3-4C refrigerated",
         "notes": "Divide into balls before retarding for the most even fermentation."},
        {"stage": "Temper", "duration": "1.5-2 h", "temperature": "room temp",
         "notes": "Bring balls back to room temperature before shaping."},
        common_bake,
    ]


def compute_recipe(
    *,
    flours: list[dict[str, Any]],
    technique: str,
    style: str = "custom",
    style_defaults: dict[str, Any] | None = None,
    hydration_pct: float | None = None,
    salt_pct: float | None = None,
    oil_pct: float | None = None,
    yeast_pct: float | None = None,
    ball_weight_g: float | None = None,
    poolish_percentage: float | None = None,
    biga_percentage: float | None = None,
    sourdough_percentage: float | None = None,
) -> dict[str, Any]:
    """Computes the dough formula for a SINGLE dough ball of `ball_weight_g` grams -
    this is the reusable "recipe", independent of how many balls you actually want to
    make. Use scale_recipe() to expand it into a batch of N balls.

    style_defaults lets callers pass an already-resolved style (e.g. fetched from the
    Cosmos-backed StyleStore in styles.py) instead of looking it up in the in-memory
    STYLE_LIBRARY seed data below.

    poolish_percentage/biga_percentage/sourdough_percentage are each the preferment's
    baker's percentage (grams of preferment flour per 100g of total flour) - only the
    one matching `technique` has any effect, and each falls back to a sane default
    (40% for poolish/biga, 20% for sourdough) when left unset.
    """
    if technique not in TECHNIQUES:
        raise ValueError(f"unknown technique '{technique}', expected one of {TECHNIQUES}")
    if style_defaults is None:
        if style not in STYLE_LIBRARY:
            raise ValueError(f"unknown style '{style}', expected one of {list(STYLE_LIBRARY)}")
        style_defaults = STYLE_LIBRARY[style]

    flours_norm, warnings = normalize_flours(flours)

    hydration = hydration_pct if hydration_pct is not None else style_defaults["hydration_pct"]
    salt = salt_pct if salt_pct is not None else style_defaults["salt_pct"]
    oil = oil_pct if oil_pct is not None else style_defaults.get("oil_pct", 0.0)
    ball_weight = ball_weight_g if ball_weight_g is not None else style_defaults.get("ball_weight_g", 250.0)

    # One ball's dough mass = flour + water + salt + oil (yeast/starter mass reported
    # separately, since for preferment techniques it is drawn from the flour/water
    # already counted).
    parts = 1 + hydration / 100 + salt / 100 + oil / 100
    flour_total_g = ball_weight / parts
    water_total_g = flour_total_g * hydration / 100
    salt_g = flour_total_g * salt / 100
    oil_g = flour_total_g * oil / 100 if oil else 0.0

    leavening, leavening_warnings = _leavening(
        technique, flour_total_g, water_total_g, yeast_pct,
        poolish_pct_override=poolish_percentage,
        biga_pct_override=biga_percentage,
        sourdough_pct_override=sourdough_percentage,
    )
    warnings += leavening_warnings

    flours_out = [
        {**f, "grams": round(flour_total_g * f["percent"] / 100, 1)}
        for f in flours_norm
    ]

    ingredients_per_ball = {
        "flour_g": round(flour_total_g, 1),
        "water_g": round(water_total_g, 1),
        "salt_g": round(salt_g, 1),
        "oil_g": round(oil_g, 1),
    }

    return {
        "flours": flours_out,
        "technique": technique,
        "hydration_pct": hydration,
        "salt_pct": salt,
        "oil_pct": oil,
        "leavening": leavening,
        "ball_weight_g": ball_weight,
        "ingredients_per_ball": ingredients_per_ball,
        "fermentation_schedule": _fermentation_schedule(technique),
        "style": style,
        "style_attribution": {
            "label": style_defaults["label"],
            "author": style_defaults["author"],
            "book": style_defaults["book"],
            "suggested_flours": style_defaults["suggested_flours"],
            "notes": style_defaults["notes"],
        },
        "warnings": warnings,
    }


# leavening dict keys that hold gram quantities and need scaling with batch size (the
# rest - "type", "rest_hours", "percent_of_flour", "note" - are ratios/text, unaffected).
_LEAVENING_GRAM_KEYS = (
    "grams", "preferment_flour_g", "preferment_water_g", "preferment_yeast_g",
    "remaining_flour_g", "remaining_water_g",
)


def scale_recipe(recipe: dict[str, Any], num_balls: int) -> dict[str, Any]:
    """Expands a single-ball recipe (as returned by compute_recipe(), or a saved
    recipe fetched from a PizzaRepository - both are per-one-ball formulas) into a
    batch of `num_balls` balls. Percentages, technique, fermentation schedule, and
    style attribution don't change with batch size; ingredients_per_ball is left
    untouched too, so it stays a stable per-ball reference regardless of num_balls.
    """
    if num_balls < 1:
        raise ValueError("num_balls must be at least 1")
    scaled = dict(recipe)
    scaled["num_balls"] = num_balls
    scaled["total_dough_g"] = round(recipe["ball_weight_g"] * num_balls, 1)
    scaled["flours"] = [{**f, "grams": round(f["grams"] * num_balls, 1)} for f in recipe["flours"]]
    scaled["leavening"] = {
        k: (round(v * num_balls, 2) if k in _LEAVENING_GRAM_KEYS else v)
        for k, v in recipe["leavening"].items()
    }
    scaled["ingredients_total"] = {k: round(v * num_balls, 1) for k, v in recipe["ingredients_per_ball"].items()}
    return scaled
