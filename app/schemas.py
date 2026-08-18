from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    """A recipe's preferment - either described inline as one or more named components
    (e.g. biga 60% / poolish 40%), or by referencing a reusable blend from
    GET /pre-ferment-types via `type_id`. Either way, the engine computes ONE aggregate
    preferment formula; named components are descriptive/echoed metadata only, never
    computed separately."""

    type_id: str | None = Field(
        default=None,
        description="References a saved blend from GET /pre-ferment-types instead of "
                    "describing components inline. Set this or `components`, not both.",
    )
    components: list[PreFermentComponent] | None = Field(
        default=None,
        description="Inline named components, e.g. [{'name': 'biga', 'percentage': 60}, "
                    "{'name': 'poolish', 'percentage': 40}]. Percentages must sum to 100. "
                    "Set this or `type_id`, not both.",
    )
    percentage: float = Field(
        default=40.0, ge=0, le=100,
        description="Baker's % of total flour built into the preferment (grams of preferment "
                    "flour per 100g of total flour). Defaults to 40.",
    )

    @model_validator(mode="after")
    def _validate_components(self) -> "PreFerment":
        if bool(self.type_id) == bool(self.components):
            raise ValueError("set exactly one of pre_ferment.type_id or pre_ferment.components")
        if self.components is not None:
            total = sum(c.percentage for c in self.components)
            if abs(total - 100.0) > 0.5:
                raise ValueError(f"pre_ferment.components percentages must sum to 100 (got {total:.1f})")
        return self


class RecipeGenerateRequest(BaseModel):
    """Describes the dough formula for a single ball - how many balls you want is a
    separate, query-time concern (see the `num_balls` query param on the /recipes
    endpoints), not part of the saved formula."""

    name: str | None = None
    ingredients: Ingredients
    pre_ferment: PreFerment | None = Field(
        default=None,
        description="Omit for a plain commercial-yeast dough. Set to build a preferment - "
                    "either inline named components or a type_id reference (see PreFerment).",
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
