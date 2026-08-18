"""International flour catalogue.

Every flour cited when creating a recipe (POST /recipes, /recipes/generate, and the
agent's generate/save tools) is identified by its `pizza_flours_id` field, which must
resolve to one of the entries below - matched against the entry's id or any of its
localized names/codes, case-insensitively - so a caller can use whatever name or type
code their country uses ("00", "farina 00", "weizenmehl 405", "t45", "405", ... all
resolve to the same flour). Callers may additionally pass `ash%`, the flour's ash
content, which is cross-checked against the resolved entry's ash_min_pct/ash_max_pct
(when tracked) and used to disambiguate `pizza_flours_id`s that match more than one
entry.

Ash content (`ash_min_pct`/`ash_max_pct`, in % per 100g of flour) is only tracked for
flours covered by WHEAT_CLASSIFICATIONS below (the soft-wheat refinement grades,
rye, spelt) - it's the milling-refinement indicator behind systems like Italy's
00/0/1/2/integrale, Germany's 405-1600, and France's T45-T150. Flours outside that
table (durum, ancient wheats, rice, legumes, starches, ...) have no ash field.

Each catalogue entry also carries its own top-level `pizza_flours_id` (mirroring `id`)
and `description` (mirroring `notes` where set, else unset) - not to be confused with
the same-named fields on a recipe request's flours[] entries (a request's
pizza_flours_id is the caller-supplied lookup key; a catalogue entry's is the resolved
id echoed back. A request's description is a free-text brand/product note; a catalogue
entry's is the flour type's own descriptive note).

FLOUR_CATALOG is seed data. When DB_BACKEND=cosmos, it's written into its own Cosmos
container (COSMOS_FLOURS_CONTAINER, default "pizza_flours") on first use and served
from there afterwards. Non-Cosmos backends (local dev, tests) just serve the seed data
directly. A container seeded before the ash
fields (or pizza_flours_id/description) were added won't pick them up automatically
(seeding only runs when the container is empty) - see scripts/backfill_flour_ash.py
and scripts/backfill_flour_pizza_flours_id.py to update it in place.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .config import Settings

# Ash-content (mg/100g) correspondence tables between national flour type systems -
# reference data only (not used for matching); stored alongside the catalogue in
# Cosmos as a single "_reference" document. Sources: Italian DPR 187/2001, German DIN
# 10355, French Calvel classification, Swiss DFI ordinance.
WHEAT_CLASSIFICATIONS: dict[str, Any] = {
    "note": "Correspondence by ash content (mg per 100g of flour). Sources: Italian "
            "DPR 187/2001, German DIN 10355, French Calvel classification, Swiss DFI ordinance.",
    "soft_wheat": [
        {"ash_min_mg": 0, "ash_max_mg": 550, "it": "00", "fr": "T45", "de": "405", "ch": "400",
         "ch_name": "farine fleur", "us": "pastry/cake flour"},
        {"ash_min_mg": 500, "ash_max_mg": 650, "it": "0", "fr": "T55", "de": "550", "ch": "550",
         "ch_name": "farine blanche", "us": "all-purpose/bread flour"},
        {"ash_min_mg": 620, "ash_max_mg": 800, "it": "1", "fr": "T65", "de": "812", "ch": "720",
         "ch_name": "farine mi-blanche", "us": "high-extraction flour"},
        {"ash_min_mg": 750, "ash_max_mg": 950, "it": "2", "fr": "T80", "de": "812", "ch": "720",
         "ch_name": "farine bise", "us": "high-extraction flour"},
        {"ash_min_mg": 900, "ash_max_mg": 1200, "it": "2", "fr": "T110", "de": "1050", "ch": "1100",
         "ch_name": "farine bise", "us": "first clear flour"},
        {"ash_min_mg": 1200, "ash_max_mg": 1800, "it": "integrale", "fr": "T150", "de": "1600",
         "ch": "1900", "ch_name": "farine complète", "us": "whole wheat"},
        {"ash_min_mg": 1700, "ash_max_mg": 2100, "it": "integrale", "fr": "T150", "de": "1700",
         "ch": "1900", "ch_name": "farine complète", "us": "whole wheat"},
    ],
    "rye_germany": [
        {"type": "815", "ash_min_mg": 700, "ash_max_mg": 910},
        {"type": "997", "ash_min_mg": 910, "ash_max_mg": 1150},
        {"type": "1150", "ash_min_mg": 1110, "ash_max_mg": 1300},
        {"type": "1370", "ash_min_mg": 1300, "ash_max_mg": 1600},
        {"type": "1740", "ash_min_mg": 1600, "ash_max_mg": 2000},
    ],
    "rye_france": [
        {"type": "T70", "ash_min_mg": 600, "ash_max_mg": 1000},
        {"type": "T85", "ash_min_mg": 750, "ash_max_mg": 1250},
        {"type": "T130", "ash_min_mg": 1200, "ash_max_mg": 1500},
        {"type": "T170", "ash_min_mg": 1500, "ash_max_mg": 2000},
    ],
    "spelt_germany": [
        {"type": "630", "ash_max_mg": 700},
        {"type": "812", "ash_max_mg": 900},
        {"type": "1050", "ash_max_mg": 1200},
    ],
}

STRENGTH_NOTE = (
    "Ash type does not indicate strength. For bread/pizza also track W (240-350 for "
    "long fermentation) or protein_pct (12-14%)."
)

FLOUR_CATALOG: list[dict[str, Any]] = [
    {"id": "soft_wheat_00", "category": "wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "ash_min_pct": 0.00, "ash_max_pct": 0.55,
     "names": {"en": "Soft wheat flour type 00", "it": "Farina 00", "fr": "Farine T45", "de": "Weizenmehl 405"}},
    {"id": "soft_wheat_0", "category": "wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "ash_min_pct": 0.50, "ash_max_pct": 0.65,
     "names": {"en": "Soft wheat flour type 0", "it": "Farina 0", "fr": "Farine T55", "de": "Weizenmehl 550"}},
    {"id": "soft_wheat_1", "category": "wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "ash_min_pct": 0.62, "ash_max_pct": 0.80,
     "names": {"en": "Soft wheat flour type 1", "it": "Farina tipo 1", "fr": "Farine T65", "de": "Weizenmehl 812"}},
    {"id": "soft_wheat_2", "category": "wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "ash_min_pct": 0.75, "ash_max_pct": 0.95,
     "names": {"en": "Soft wheat flour type 2", "it": "Farina tipo 2", "fr": "Farine T80/T110", "de": "Weizenmehl 1050"}},
    {"id": "whole_wheat", "category": "wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "ash_min_pct": 1.20, "ash_max_pct": 1.80,
     "names": {"en": "Whole wheat flour", "it": "Farina integrale", "fr": "Farine T150", "de": "Weizenvollkornmehl"}},
    {"id": "manitoba", "category": "wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "notes": "High strength (W>350), any refinement type",
     "names": {"en": "Manitoba flour", "it": "Farina Manitoba", "fr": "Farine de gruau", "de": "Manitobamehl"}},
    {"id": "durum_semolina", "category": "durum_wheat", "gluten": True, "bread": True, "pizza": False, "max_blend_pct": 100,
     "names": {"en": "Durum wheat semolina", "it": "Semola di grano duro", "fr": "Semoule de blé dur", "de": "Hartweizengriess"}},
    {"id": "durum_rimacinata", "category": "durum_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "notes": "Pane di Altamura, Sicilian bread",
     "names": {"en": "Re-milled durum semolina", "it": "Semola rimacinata", "fr": "Semoule fine de blé dur", "de": "Hartweizenmehl"}},
    {"id": "spelt", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "ash_min_pct": 0.00, "ash_max_pct": 1.20,
     "names": {"en": "Spelt flour", "it": "Farina di farro spelta", "fr": "Farine d'épeautre", "de": "Dinkelmehl"}},
    {"id": "einkorn", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "notes": "Weak gluten",
     "names": {"en": "Einkorn flour", "it": "Farina di farro monococco", "fr": "Farine de petit épeautre", "de": "Einkornmehl"}},
    {"id": "emmer", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Emmer flour", "it": "Farina di farro dicocco", "fr": "Farine d'amidonnier", "de": "Emmermehl"}},
    {"id": "khorasan", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Khorasan (Kamut) flour", "it": "Farina di grano Khorasan", "fr": "Farine de Khorasan (Kamut)", "de": "Kamutmehl"}},
    {"id": "maiorca", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "notes": "Sicilian soft wheat landrace, weak, traditional for pastry",
     "names": {"en": "Maiorca wheat flour", "it": "Farina di Maiorca"}},
    {"id": "tumminia", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "notes": "Sicilian durum landrace (pane nero di Castelvetrano)",
     "names": {"en": "Tumminia wheat flour", "it": "Farina di Tumminia"}},
    {"id": "russello", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Russello wheat flour", "it": "Farina di Russello"}},
    {"id": "perciasacchi", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Perciasacchi wheat flour", "it": "Farina di Perciasacchi"}},
    {"id": "senatore_cappelli", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "notes": "Durum landrace", "names": {"en": "Senatore Cappelli flour", "it": "Farina Senatore Cappelli"}},
    {"id": "verna", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Verna wheat flour", "it": "Farina di grano Verna"}},
    {"id": "gentil_rosso", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Gentil Rosso wheat flour", "it": "Farina Gentil Rosso"}},
    {"id": "solina", "category": "ancient_wheat", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 100,
     "names": {"en": "Solina wheat flour", "it": "Farina di Solina"}},
    {"id": "rye", "category": "cereal_gluten", "gluten": True, "bread": True, "pizza": False, "max_blend_pct": 100,
     "notes": "German types 815-1740, French T70-T170",
     "ash_min_pct": 0.60, "ash_max_pct": 2.00,
     "names": {"en": "Rye flour", "it": "Farina di segale", "fr": "Farine de seigle", "de": "Roggenmehl"}},
    {"id": "barley", "category": "cereal_gluten", "gluten": True, "bread": True, "pizza": False, "max_blend_pct": 30,
     "names": {"en": "Barley flour", "it": "Farina d'orzo", "fr": "Farine d'orge", "de": "Gerstenmehl"}},
    {"id": "oat", "category": "cereal_gluten", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 30,
     "notes": "Contains avenin; often certified GF",
     "names": {"en": "Oat flour", "it": "Farina d'avena", "fr": "Farine d'avoine", "de": "Hafermehl"}},
    {"id": "triticale", "category": "cereal_gluten", "gluten": True, "bread": True, "pizza": False, "max_blend_pct": 100,
     "names": {"en": "Triticale flour", "it": "Farina di triticale", "fr": "Farine de triticale", "de": "Triticalemehl"}},
    {"id": "rice_white", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 30,
     "notes": "Base of most GF blends",
     "names": {"en": "White rice flour", "it": "Farina di riso", "fr": "Farine de riz", "de": "Reismehl"}},
    {"id": "rice_brown", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 30,
     "names": {"en": "Brown rice flour", "it": "Farina di riso integrale", "fr": "Farine de riz complet", "de": "Vollkornreismehl"}},
    {"id": "rice_glutinous", "category": "cereal_gf", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Glutinous rice flour", "it": "Farina di riso glutinoso", "fr": "Farine de riz gluant", "de": "Klebreismehl"}},
    {"id": "corn_fioretto", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 30,
     "names": {"en": "Fine cornmeal", "it": "Farina di mais fioretto", "fr": "Farine de maïs fine", "de": "Maismehl fein"}},
    {"id": "corn_fumetto", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 30,
     "names": {"en": "Extra-fine corn flour", "it": "Farina di mais fumetto", "fr": "Farine de maïs extra-fine", "de": "Maismehl extrafein"}},
    {"id": "corn_bramata", "category": "cereal_gf", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 20,
     "notes": "Coarse, polenta",
     "names": {"en": "Coarse cornmeal (polenta)", "it": "Farina di mais bramata", "fr": "Polenta", "de": "Polenta / Maisgriess"}},
    {"id": "millet", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 25,
     "names": {"en": "Millet flour", "it": "Farina di miglio", "fr": "Farine de millet", "de": "Hirsemehl"}},
    {"id": "sorghum", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 30,
     "names": {"en": "Sorghum flour", "it": "Farina di sorgo", "fr": "Farine de sorgho", "de": "Sorghummehl"}},
    {"id": "teff", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 30,
     "notes": "Injera at 100%", "names": {"en": "Teff flour", "it": "Farina di teff", "fr": "Farine de teff", "de": "Teffmehl"}},
    {"id": "fonio", "category": "cereal_gf", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 25,
     "names": {"en": "Fonio flour", "it": "Farina di fonio", "fr": "Farine de fonio", "de": "Foniomehl"}},
    {"id": "buckwheat", "category": "pseudocereal", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 30,
     "names": {"en": "Buckwheat flour", "it": "Farina di grano saraceno", "fr": "Farine de sarrasin", "de": "Buchweizenmehl"}},
    {"id": "quinoa", "category": "pseudocereal", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Quinoa flour", "it": "Farina di quinoa", "fr": "Farine de quinoa", "de": "Quinoamehl"}},
    {"id": "amaranth", "category": "pseudocereal", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Amaranth flour", "it": "Farina di amaranto", "fr": "Farine d'amarante", "de": "Amaranthmehl"}},
    {"id": "chickpea", "category": "legume", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 25,
     "notes": "Farinata/socca at 100%",
     "names": {"en": "Chickpea flour", "it": "Farina di ceci", "fr": "Farine de pois chiche", "de": "Kichererbsenmehl"}},
    {"id": "fava", "category": "legume", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 15,
     "names": {"en": "Fava bean flour", "it": "Farina di fave", "fr": "Farine de fève", "de": "Ackerbohnenmehl"}},
    {"id": "lentil", "category": "legume", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Lentil flour", "it": "Farina di lenticchie", "fr": "Farine de lentille", "de": "Linsenmehl"}},
    {"id": "pea", "category": "legume", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Pea flour", "it": "Farina di piselli", "fr": "Farine de pois", "de": "Erbsenmehl"}},
    {"id": "soy", "category": "legume", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 15,
     "names": {"en": "Soy flour", "it": "Farina di soia", "fr": "Farine de soja", "de": "Sojamehl"}},
    {"id": "lupin", "category": "legume", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 15,
     "notes": "Allergen", "names": {"en": "Lupin flour", "it": "Farina di lupini", "fr": "Farine de lupin", "de": "Lupinenmehl"}},
    {"id": "almond", "category": "nut_seed", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Almond flour", "it": "Farina di mandorle", "fr": "Farine d'amande", "de": "Mandelmehl"}},
    {"id": "hazelnut", "category": "nut_seed", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Hazelnut flour", "it": "Farina di nocciole", "fr": "Farine de noisette", "de": "Haselnussmehl"}},
    {"id": "coconut", "category": "nut_seed", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 15,
     "notes": "Very absorbent", "names": {"en": "Coconut flour", "it": "Farina di cocco", "fr": "Farine de coco", "de": "Kokosmehl"}},
    {"id": "chestnut", "category": "nut_seed", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 25,
     "notes": "Castagnaccio at 100%",
     "names": {"en": "Chestnut flour", "it": "Farina di castagne", "fr": "Farine de châtaigne", "de": "Kastanienmehl"}},
    {"id": "flaxseed", "category": "nut_seed", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 10,
     "notes": "Also egg substitute/binder",
     "names": {"en": "Flaxseed meal", "it": "Farina di semi di lino", "fr": "Farine de lin", "de": "Leinsamenmehl"}},
    {"id": "hemp", "category": "nut_seed", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 10,
     "names": {"en": "Hemp flour", "it": "Farina di canapa", "fr": "Farine de chanvre", "de": "Hanfmehl"}},
    {"id": "sunflower_seed", "category": "nut_seed", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 15,
     "names": {"en": "Sunflower seed flour", "it": "Farina di semi di girasole", "fr": "Farine de tournesol", "de": "Sonnenblumenkernmehl"}},
    {"id": "sesame", "category": "nut_seed", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 10,
     "names": {"en": "Sesame flour", "it": "Farina di sesamo", "fr": "Farine de sésame", "de": "Sesammehl"}},
    {"id": "potato_flour", "category": "tuber_root", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 20,
     "names": {"en": "Potato flour", "it": "Farina di patate", "fr": "Farine de pomme de terre", "de": "Kartoffelmehl"}},
    {"id": "potato_starch", "category": "tuber_root", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 20,
     "names": {"en": "Potato starch", "it": "Fecola di patate", "fr": "Fécule de pomme de terre", "de": "Kartoffelstärke"}},
    {"id": "tapioca", "category": "tuber_root", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 25,
     "notes": "Key in GF pizza blends; pão de queijo",
     "names": {"en": "Tapioca starch/flour", "it": "Farina di tapioca", "fr": "Fécule de tapioca", "de": "Tapiokastärke"}},
    {"id": "cassava", "category": "tuber_root", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 30,
     "names": {"en": "Cassava flour", "it": "Farina di manioca", "fr": "Farine de manioc", "de": "Maniokmehl"}},
    {"id": "arrowroot", "category": "tuber_root", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 15,
     "names": {"en": "Arrowroot starch", "it": "Amido di arrowroot", "fr": "Arrow-root", "de": "Pfeilwurzelstärke"}},
    {"id": "sweet_potato", "category": "tuber_root", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Sweet potato flour", "it": "Farina di patata dolce", "fr": "Farine de patate douce", "de": "Süsskartoffelmehl"}},
    {"id": "corn_starch", "category": "starch", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 20,
     "names": {"en": "Corn starch", "it": "Amido di mais (maizena)", "fr": "Fécule de maïs (Maïzena)", "de": "Maisstärke"}},
    {"id": "wheat_starch", "category": "starch", "gluten": False, "bread": True, "pizza": True, "max_blend_pct": 20,
     "notes": "GF only if certified",
     "names": {"en": "Wheat starch", "it": "Amido di frumento", "fr": "Amidon de blé", "de": "Weizenstärke"}},
    {"id": "carob", "category": "other", "gluten": False, "bread": False, "pizza": False, "max_blend_pct": 10,
     "names": {"en": "Carob flour", "it": "Farina di carrube", "fr": "Farine de caroube", "de": "Johannisbrotmehl"}},
    {"id": "banana_green", "category": "other", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Green banana flour", "it": "Farina di banana verde", "fr": "Farine de banane verte", "de": "Bananenmehl"}},
    {"id": "acorn", "category": "other", "gluten": False, "bread": True, "pizza": False, "max_blend_pct": 20,
     "names": {"en": "Acorn flour", "it": "Farina di ghiande", "fr": "Farine de gland", "de": "Eichelmehl"}},
    {"id": "malted_barley", "category": "other", "gluten": True, "bread": True, "pizza": True, "max_blend_pct": 2,
     "notes": "Diastatic malt, dough improver",
     "names": {"en": "Diastatic malt flour", "it": "Malto diastasico", "fr": "Farine de malt", "de": "Malzmehl"}},
]

# Mirrors the flours[].pizza_flours_id/description fields used on recipe requests (see
# app/schemas.py) onto every catalogue entry, so a client can read the same field names
# from GET /recipes/flours: pizza_flours_id is just the entry's own id; description is
# copied from notes where an entry has one, else left unset.
for _flour in FLOUR_CATALOG:
    _flour["pizza_flours_id"] = _flour["id"]
    _flour["description"] = _flour.get("notes")
del _flour

# Bare national type-code aliases (from WHEAT_CLASSIFICATIONS) that aren't already
# spelled out in a flour's own `names` above - e.g. so "00", "T45", or "405" alone
# (not just "Farina 00"/"Farine T45"/"Weizenmehl 405") resolve to soft_wheat_00. Each
# code is only ever assigned to a single flour id, even where the source ash tables
# overlap (e.g. rye's German/French codes all fold onto the single "rye" entry, since
# this catalogue doesn't split rye by ash content).
_EXTRA_ALIASES: dict[str, list[str]] = {
    "soft_wheat_00": ["00", "t45", "405", "400", "pastry/cake flour", "farine fleur"],
    "soft_wheat_0": ["0", "t55", "550", "all-purpose/bread flour", "farine blanche"],
    "soft_wheat_1": ["1", "t65", "720", "high-extraction flour", "farine mi-blanche"],
    "soft_wheat_2": ["2", "t80", "t110", "1100", "first clear flour", "farine bise"],
    "whole_wheat": ["integrale", "t150", "1600", "1700", "1900", "farine complète", "farine complete"],
    "rye": ["815", "997", "1150", "1370", "1740", "t70", "t85", "t130", "t170"],
}


def _match_keys(flour: dict[str, Any]) -> set[str]:
    keys = {flour["id"].strip().lower()}
    for name in flour.get("names", {}).values():
        if name:
            keys.add(name.strip().lower())
    for alias in _EXTRA_ALIASES.get(flour["id"], []):
        keys.add(alias)
    return keys


def _ash_in_range(flour: dict[str, Any], ash_pct: float) -> bool:
    ash_min, ash_max = flour.get("ash_min_pct"), flour.get("ash_max_pct")
    return ash_min is not None and ash_max is not None and ash_min <= ash_pct <= ash_max


class FlourCatalogStore(ABC):
    @abstractmethod
    def list(self) -> list[dict[str, Any]]: ...

    def resolve(self, description: str, ash_pct: float | None = None) -> dict[str, Any] | None:
        needle = description.strip().lower()
        matches = [flour for flour in self.list() if needle in _match_keys(flour)]
        if not matches:
            return None
        if ash_pct is not None and len(matches) > 1:
            for flour in matches:
                if _ash_in_range(flour, ash_pct):
                    return flour
        return matches[0]


class InMemoryFlourCatalogStore(FlourCatalogStore):
    def list(self):
        return FLOUR_CATALOG


class CosmosFlourCatalogStore(FlourCatalogStore):
    _REFERENCE_ID = "_reference"

    def __init__(self, settings: Settings):
        from azure.cosmos import CosmosClient, PartitionKey

        client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.create_database_if_not_exists(id=settings.cosmos_database)
        self._container = database.create_container_if_not_exists(
            id=settings.cosmos_flours_container, partition_key=PartitionKey(path="/id")
        )
        self._seed_if_empty()

    def _seed_if_empty(self):
        count = next(iter(self._container.query_items(
            query="SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
        )), 0)
        if count:
            return
        for flour in FLOUR_CATALOG:
            self._container.upsert_item(flour)
        self._container.upsert_item({
            "id": self._REFERENCE_ID,
            "wheat_classifications": WHEAT_CLASSIFICATIONS,
            "strength_note": STRENGTH_NOTE,
        })

    def list(self):
        items = self._container.query_items(
            query=f"SELECT * FROM c WHERE c.id != '{self._REFERENCE_ID}'",
            enable_cross_partition_query=True,
        )
        return list(items)


def build_flour_catalog_store(settings: Settings) -> FlourCatalogStore:
    if settings.db_backend == "cosmos":
        return CosmosFlourCatalogStore(settings)
    return InMemoryFlourCatalogStore()
