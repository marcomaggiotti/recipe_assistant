from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ToppingCategory = Literal["meat", "vegetable", "cheese", "sauce", "other"]


class ToppingComponent(BaseModel):
    name: str = Field(min_length=1, description="e.g. 'basil', 'pine nuts', 'lemon zest'.")
    amount: str | None = Field(default=None, description="Free-text quantity, e.g. '2 tbsp', '50g', 'to taste'.")


class ToppingCreate(BaseModel):
    name: str = Field(min_length=1, description="e.g. 'Pepperoni', 'Mushrooms', 'Mozzarella', 'Pesto'.")
    category: ToppingCategory
    vegetarian: bool = False
    vegan: bool = False
    description: str | None = Field(default=None, description="Optional free-text note, e.g. brand or prep style.")
    components: list[ToppingComponent] | None = Field(
        default=None,
        description="Set when this topping is itself a small recipe rather than a single "
                    "ingredient, e.g. Pesto = [{'name': 'basil'}, {'name': 'pine nuts'}, "
                    "{'name': 'garlic'}, {'name': 'parmesan'}, {'name': 'olive oil'}]. "
                    "Omit for a plain single-ingredient topping.",
    )


class Topping(ToppingCreate):
    id: str
    created_at: datetime


class ToppingList(BaseModel):
    items: list[Topping]
    count: int
