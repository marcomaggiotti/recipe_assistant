from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .recipe import TECHNIQUES

Technique = Literal[
    "direct", "same_day", "poolish", "biga", "sourdough",
    "cold_ferment_24h", "cold_ferment_48h", "cold_ferment_72h",
]
assert list(Technique.__args__) == TECHNIQUES  # keep schema and engine in sync


class FlourComponent(BaseModel):
    type: str = Field(min_length=1, description="e.g. 'Italian 00 flour', 'Whole wheat', 'Semola rimacinata'")
    percent: float = Field(gt=0, description="Baker's % of this flour relative to the total flour blend")


class RecipeGenerateRequest(BaseModel):
    name: str | None = None
    flours: list[FlourComponent] = Field(min_length=1)
    technique: Technique
    style: str = "custom"
    hydration_pct: float | None = Field(default=None, ge=40, le=100)
    salt_pct: float | None = Field(default=None, ge=0, le=6)
    oil_pct: float | None = Field(default=None, ge=0, le=15)
    yeast_pct: float | None = Field(default=None, ge=0, le=5)
    num_balls: int = Field(default=4, ge=1, le=50)
    ball_weight_g: float | None = Field(default=None, gt=0)


class StyleAttribution(BaseModel):
    label: str
    author: str | None
    book: str | None
    suggested_flours: list[str]
    notes: str


class GeneratedRecipe(BaseModel):
    flours: list[dict]
    technique: str
    hydration_pct: float
    salt_pct: float
    oil_pct: float
    leavening: dict
    ball_weight_g: float
    total_dough_g: float
    ingredients_total: dict
    ingredients_per_ball: dict
    fermentation_schedule: list[dict]
    style: str
    style_attribution: StyleAttribution
    warnings: list[str]


class PizzaRecipe(GeneratedRecipe):
    id: str
    name: str
    created_at: datetime


class PizzaRecipeList(BaseModel):
    items: list[PizzaRecipe]
    count: int


class StyleInfo(BaseModel):
    style: str
    technique: str
    hydration_pct: float
    salt_pct: float
    oil_pct: float
    ball_weight_g: float
    style_attribution: StyleAttribution


class AgentChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class AgentChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict] = []
