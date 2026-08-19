"""Seed data for the toppings table: a reasonably complete pizzeria topping menu, so
the service starts with something to browse/select from rather than an empty catalog.
Most entries are plain single ingredients; a few (Pesto, Ricotta with lemon zest, ...)
are "composite" - themselves a small recipe - and carry a `components` breakdown.

Seeded once, the first time the table is empty (see build_repository() in toppings.py) -
same seed-if-empty pattern used elsewhere in this repo (e.g. app/db.py's Cosmos stores).
Toppings are a mutable, user-editable catalog though (unlike the read-mostly flour/
pre-ferment catalogs), so this is just a starting menu - add, edit, or delete freely via
POST/DELETE /toppings afterward.
"""
from __future__ import annotations

from typing import Any

TOPPING_CATALOG: list[dict[str, Any]] = [
    # --- cheese ---
    {"name": "Mozzarella", "category": "cheese", "vegetarian": True, "vegan": False},
    {"name": "Fior di latte", "category": "cheese", "vegetarian": True, "vegan": False,
     "description": "Fresh cow's-milk mozzarella"},
    {"name": "Burrata", "category": "cheese", "vegetarian": True, "vegan": False,
     "description": "Added after baking"},
    {"name": "Parmesan", "category": "cheese", "vegetarian": True, "vegan": False},
    {"name": "Gorgonzola", "category": "cheese", "vegetarian": True, "vegan": False},
    {"name": "Ricotta", "category": "cheese", "vegetarian": True, "vegan": False},
    {"name": "Provolone", "category": "cheese", "vegetarian": True, "vegan": False},
    {"name": "Vegan mozzarella", "category": "cheese", "vegetarian": True, "vegan": True,
     "description": "Cashew or coconut-oil based"},

    # --- sauce ---
    {"name": "Tomato sauce", "category": "sauce", "vegetarian": True, "vegan": True},
    {"name": "White sauce (bechamel)", "category": "sauce", "vegetarian": True, "vegan": False},
    {"name": "BBQ sauce", "category": "sauce", "vegetarian": True, "vegan": True},

    # --- meat ---
    {"name": "Pepperoni", "category": "meat", "vegetarian": False, "vegan": False},
    {"name": "Prosciutto crudo", "category": "meat", "vegetarian": False, "vegan": False,
     "description": "Added after baking"},
    {"name": "Prosciutto cotto", "category": "meat", "vegetarian": False, "vegan": False},
    {"name": "Salame piccante", "category": "meat", "vegetarian": False, "vegan": False},
    {"name": "Nduja", "category": "meat", "vegetarian": False, "vegan": False,
     "description": "Spreadable spicy Calabrian sausage"},
    {"name": "Italian sausage", "category": "meat", "vegetarian": False, "vegan": False},
    {"name": "Bacon", "category": "meat", "vegetarian": False, "vegan": False},
    {"name": "Chicken", "category": "meat", "vegetarian": False, "vegan": False},

    # --- other (seafood, oils, condiments) ---
    {"name": "Anchovies", "category": "other", "vegetarian": False, "vegan": False},
    {"name": "Tuna", "category": "other", "vegetarian": False, "vegan": False},
    {"name": "Olive oil", "category": "other", "vegetarian": True, "vegan": True, "description": "Drizzle"},
    {"name": "Truffle oil", "category": "other", "vegetarian": True, "vegan": True, "description": "Drizzle"},
    {"name": "Chili flakes", "category": "other", "vegetarian": True, "vegan": True},

    # --- vegetable ---
    {"name": "Mushrooms", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Bell peppers", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Red onions", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Black olives", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Cherry tomatoes", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Artichokes", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Basil", "category": "vegetable", "vegetarian": True, "vegan": True, "description": "Fresh, added after baking"},
    {"name": "Arugula", "category": "vegetable", "vegetarian": True, "vegan": True, "description": "Fresh, added after baking"},
    {"name": "Capers", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Eggplant", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Zucchini", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Spinach", "category": "vegetable", "vegetarian": True, "vegan": True},
    {"name": "Sweet corn", "category": "vegetable", "vegetarian": True, "vegan": True},

    # --- composite toppings (themselves a small recipe) ---
    {
        "name": "Pesto", "category": "sauce", "vegetarian": True, "vegan": False,
        "description": "Genovese basil pesto",
        "components": [
            {"name": "basil"}, {"name": "pine nuts"}, {"name": "garlic"},
            {"name": "parmesan"}, {"name": "olive oil"}, {"name": "salt"},
        ],
    },
    {
        "name": "Ricotta with lemon zest", "category": "cheese", "vegetarian": True, "vegan": False,
        "description": "Dolloped on after baking",
        "components": [
            {"name": "ricotta"}, {"name": "lemon zest"}, {"name": "black pepper"}, {"name": "olive oil"},
        ],
    },
    {
        "name": "Caponata", "category": "vegetable", "vegetarian": True, "vegan": True,
        "description": "Sicilian sweet-and-sour eggplant relish",
        "components": [
            {"name": "eggplant"}, {"name": "celery"}, {"name": "tomato"}, {"name": "capers"},
            {"name": "green olives"}, {"name": "red wine vinegar"}, {"name": "sugar"},
        ],
    },
    {
        "name": "Salsa verde", "category": "sauce", "vegetarian": False, "vegan": False,
        "description": "Italian green herb sauce",
        "components": [
            {"name": "parsley"}, {"name": "capers"}, {"name": "anchovy"},
            {"name": "garlic"}, {"name": "olive oil"}, {"name": "red wine vinegar"},
        ],
    },
]
