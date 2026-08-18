from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class PreFermentComponent(BaseModel):
    name: str = Field(min_length=1, description="e.g. 'biga', 'sourdough', 'poolish'.")
    percentage: float = Field(
        gt=0, le=100, description="This component's share of the preferment mix itself (not of "
                                   "total dough flour), e.g. biga 60 / poolish 40.",
    )


class PreFerment(BaseModel):
    """A recipe's preferment - references a reusable blend (one or more named
    components, e.g. biga 60% / poolish 40%) saved via POST /pre-ferment-types. The
    engine computes ONE aggregate preferment formula from the referenced blend; its
    named components are descriptive/echoed metadata only, never computed separately."""

    type_id: str = Field(
        min_length=1,
        description="References a saved blend from GET /pre-ferment-types, e.g. 'biga100' "
                    "or 'biga60_poolish40'.",
    )
    percentage: float = Field(
        default=40.0, ge=0, le=100,
        description="Baker's % of total flour built into the preferment (grams of preferment "
                    "flour per 100g of total flour). Defaults to 40.",
    )


class RecipeGenerateRequest(BaseModel):
    """Describes the dough formula for a single ball - how many balls you want is a
    separate, query-time concern (see the `num_balls` query param on the /recipes
    endpoints), not part of the saved formula."""

    name: str | None = None
    ingredients: Ingredients
    pre_ferment: PreFerment | None = Field(
        default=None,
        description="Omit for a plain commercial-yeast dough. Set to build a preferment "
                    "from a saved blend (see PreFerment.type_id).",
    )
    hydration_pct: float | None = Field(default=None, ge=0, le=100)
    salt_pct: float | None = Field(default=None, ge=0)
    oil_pct: float | None = Field(default=None, ge=0)
    yeast_pct: float | None = Field(default=None, ge=0)
    ball_weight_g: float | None = Field(default=None, gt=0)


class GeneratedRecipe(BaseModel):
    """A single-ball formula (ball_weight_g), scaled to num_balls balls (default 1,
    set via the `num_balls` query param) - ingredients.flours[].grams, leavening's gram
    fields, and ingredients_total reflect the full num_balls batch; ingredients_per_ball
    is the constant per-ball reference regardless of num_balls.

    Note ingredients (the flour blend, {"flours": [...]}) and ingredients_per_ball/
    ingredients_total (computed flour/water/salt/oil weights) are different things
    that happen to share a name prefix - not a typo."""

    ingredients: dict
    pre_ferment: dict | None
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
    warnings: list[str]


class PizzaRecipe(GeneratedRecipe):
    id: str
    name: str
    created_at: datetime


class PizzaRecipeList(BaseModel):
    items: list[PizzaRecipe]
    count: int


class AgentChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class AgentChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict] = []
