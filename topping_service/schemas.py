from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ToppingCategory = Literal["meat", "vegetable", "cheese", "sauce", "other"]


class ToppingCreate(BaseModel):
    name: str = Field(min_length=1, description="e.g. 'Pepperoni', 'Mushrooms', 'Mozzarella'.")
    category: ToppingCategory
    vegetarian: bool = False
    vegan: bool = False
    description: str | None = Field(default=None, description="Optional free-text note, e.g. brand or prep style.")


class Topping(ToppingCreate):
    id: str
    created_at: datetime


class ToppingList(BaseModel):
    items: list[Topping]
    count: int
