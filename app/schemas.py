from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .recipe import PREFERMENT_TECHNIQUES, TECHNIQUES

Technique = Literal[
    "direct", "same_day", "poolish", "biga", "sourdough",
    "cold_ferment_24h", "cold_ferment_48h", "cold_ferment_72h",
]
assert list(Technique.__args__) == TECHNIQUES  # keep schema and engine in sync

PreFermentType = Literal["poolish", "biga", "sourdough"]
assert list(PreFermentType.__args__) == list(PREFERMENT_TECHNIQUES)  # keep schema and engine in sync


class FlourComponent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ash_pct: float | None = Field(
        default=None, alias="ash%", ge=0, le=3,
        description="Ash content % per 100g of flour (e.g. 0.55 for Italian Tipo 00, per DPR "
                    "187/2001). Only meaningful for milled wheat flours; leave unset for flours "
                    "without a tracked ash grade (rice, legumes, starches, ...). When set, it is "
                    "cross-checked against the resolved flour's ash range and used to disambiguate "
                    "'pizza_flours_id's that match more than one catalogue entry.",
    )
    pizza_flours_id: str = Field(
        min_length=1,
        description="Flour name, e.g. 'Italian 00 flour', 'Whole wheat', 'Semola rimacinata'. Must "
                    "resolve to an entry in GET /recipes/flours (its id or one of its localized "
                    "names/codes).",
    )
    description: str | None = Field(
        default=None,
        description="Free-text note for the specific brand/product used for this flour, e.g. "
                    "'Semola Caputo' or 'Naturaplan Bio CH Weissmehl Coop'. Purely informational - "
                    "not matched against the catalogue and not used to resolve pizza_flours_id.",
    )
    percent: float = Field(gt=0, description="Baker's % of this flour relative to the total flour blend")


class Ingredients(BaseModel):
    flours: list[FlourComponent] = Field(min_length=1)


class PreFerment(BaseModel):
    type: PreFermentType
    percentage: float = Field(
        ge=0, le=100,
        description="Baker's % of the preferment/starter relative to total flour weight (grams of "
                    "preferment flour, or starter, per 100g of total flour). Defaults to 40 for "
                    "poolish/biga, 20 for sourdough, when this entry is omitted entirely.",
    )


class RecipeGenerateRequest(BaseModel):
    """Describes the dough formula for a single ball - how many balls you want is a
    separate, query-time concern (see the `num_balls` query param on the /recipes
    endpoints), not part of the saved formula."""

    name: str | None = None
    ingredients: Ingredients
    pre_ferments: list[PreFerment] = Field(
        default_factory=list, max_length=1,
        description="At most one, for now - only one preferment technique can be active per "
                    "recipe. Its `type` becomes the recipe's technique unless `technique` is also "
                    "given explicitly, in which case they must match. Omit entirely for "
                    "direct/same_day/cold_ferment_* techniques (no separate preferment).",
    )
    technique: Technique | None = Field(
        default=None,
        description="Optional when pre_ferments has an entry (inferred from its type); otherwise "
                    "defaults to 'direct'. Required only to select a non-preferment technique "
                    "(same_day, cold_ferment_24h/48h/72h) or 'direct' explicitly.",
    )
    style: str = "custom"
    hydration_pct: float | None = Field(default=None, ge=0, le=100)
    salt_pct: float | None = Field(default=None, ge=0)
    oil_pct: float | None = Field(default=None, ge=0)
    yeast_pct: float | None = Field(default=None, ge=0)
    ball_weight_g: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _resolve_technique(self) -> "RecipeGenerateRequest":
        if self.pre_ferments:
            inferred = self.pre_ferments[0].type
            if self.technique is not None and self.technique != inferred:
                raise ValueError(
                    f"technique '{self.technique}' does not match pre_ferments[0].type '{inferred}'"
                )
            self.technique = inferred
        elif self.technique is None:
            self.technique = "direct"
        return self


class StyleAttribution(BaseModel):
    label: str
    author: str | None
    book: str | None
    suggested_flours: list[str]
    notes: str


class GeneratedRecipe(BaseModel):
    """A single-ball formula (ball_weight_g), scaled to num_balls balls (default 1,
    set via the `num_balls` query param) - ingredients.flours[].grams, leavening's gram
    fields, and ingredients_total reflect the full num_balls batch; ingredients_per_ball
    is the constant per-ball reference regardless of num_balls.

    Note ingredients (the flour blend, {"flours": [...]}) and ingredients_per_ball/
    ingredients_total (computed flour/water/salt/oil weights) are different things
    that happen to share a name prefix - not a typo."""

    ingredients: dict
    pre_ferments: list[dict]
    technique: str
    hydration_pct: float
    salt_pct: float
    oil_pct: float
    leavening: dict
    ball_weight_g: float
    num_balls: int
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
