# Pizza Service (AI Agent)

FastAPI microservice that turns a **flour blend** (baker's percentages) and an optional
**pre-ferment** (a reusable named blend, e.g. biga 60% / poolish 40%) into a scaled
pizza dough recipe: ingredient weights, a preferment breakdown where relevant, and a
fermentation schedule. Also exposes a built-in AI agent endpoint (`/agent/chat`) that
can do the same from a natural-language instruction via Anthropic tool-calling.

Extracted from the [`ict_project`](https://github.com/marcomaggiotti/ict_project) monorepo
as a standalone, self-contained service (own dependencies, Dockerfile, config).

## Endpoints

| Method | Path              | Description                                                |
|--------|-------------------|--------------------------------------------------------------|
| GET    | `/health`         | Liveness check                                                |
| GET    | `/recipes/flours` | List the international flour catalogue                        |
| POST   | `/recipes/generate` | Compute a recipe (`?num_balls=N`, default 1) without saving it |
| POST   | `/recipes`        | Compute the single-ball formula and save it                   |
| GET    | `/recipes`        | List saved recipes (`limit`, `offset`)                        |
| GET    | `/recipes/{id}`   | Get one saved recipe (`?num_balls=N`, default 1)               |
| DELETE | `/recipes/{id}`   | Delete a saved recipe                                          |
| POST   | `/pre-ferment-types` | Save a reusable named pre-ferment blend (**Postgres-only**) |
| GET    | `/pre-ferment-types` | List saved pre-ferment blends (**Postgres-only**) |
| GET    | `/pre-ferment-types/{id}` | Get one saved pre-ferment blend (**Postgres-only**) |
| DELETE | `/pre-ferment-types/{id}` | Delete a saved pre-ferment blend (**Postgres-only**) |
| POST   | `/agent/chat`     | Natural-language agent chat over recipe generation/storage    |
| GET    | `/`               | Browser page - home/nav menu |
| GET    | `/flour-explorer` | Browser page - filterable thumbnail grid over the flour catalogue |
| GET    | `/flour-products/new` | Browser page - link a real product URL to a flour_catalog entry |
| GET    | `/new-recipe`     | Browser page - build and save a recipe from a flour blend |

All JSON API endpoints except `/health` require header `X-API-Key` if `API_KEY` is set
in the environment (leave it empty for local dev); the browser pages themselves never
require it (they're public HTML, not part of the JSON API surface), though the
flour-service calls they make client-side respect an optional API key entered on the
page if that service has its own `API_KEY` set.

### Browser pages

Four small, dependency-free HTML/JS pages (no frontend build step, shared styling via
`app/static/theme.css`), served directly by this FastAPI app:

- **`/`** - home page with a nav menu linking the other three, plus `/docs`.
- **`/flour-explorer`** - queries [flour-service](https://github.com/marcomaggiotti/flour_service)
  directly from the browser; filter by category, gluten, bread/pizza suitability,
  strength tier, or ash%, or look up one flour by name/national type code. Renders
  results as a thumbnail card grid. Live view, no local copy of the catalogue.
- **`/flour-products/new`** - link a real product page URL (e.g. a Migros/Coop listing)
  to a `flour_catalog` entry via flour-service's `POST /flour-products`, and see/remove
  what's already linked. Warns if flour-service is currently running with an in-memory
  backend (added products would be lost on its next restart).
- **`/new-recipe`** - build a dough formula (flour blend rows populated from
  flour-service, an optional pre-ferment referencing a saved blend - with a way to save
  a new named blend, e.g. biga 60% / poolish 40%, inline - optional hydration/salt/oil/
  yeast overrides) and save it via this service's own `POST /recipes`; shows the
  computed result and a list of recently saved recipes. Deliberately not at
  `/recipes/new` - that would collide with `GET /recipes/{item_id}`.

All of them call `flour-service` directly from client-side JS: set `FLOUR_SERVICE_URL`
to point at a different deployment (default `https://flour-service.onrender.com`), e.g.
`http://localhost:8001` if you're running flour-service locally too.

## The recipe model

A recipe is always a **single dough ball's formula** - how many balls you want is a
separate, query-time concern (`?num_balls=N` on `/recipes/generate` and
`GET /recipes/{id}`, default 1), not part of what you save. Request body for
`/recipes/generate` and `/recipes`:

```json
{
  "name": "Country Sourdough",
  "ingredients": {
    "flours": [
      {"pizza_flours_id": "soft_wheat_0", "ash%": 0.55, "description": "Strong white flour", "percent": 80},
      {"pizza_flours_id": "whole_wheat", "ash%": 1.30, "description": "Whole wheat flour", "percent": 20}
    ]
  },
  "pre_ferment": {
    "type_id": "biga60_poolish40",
    "percentage": 35
  },
  "hydration_pct": 75,
  "salt_pct": 2,
  "oil_pct": 0,
  "ball_weight_g": 900
}
```

- `ingredients.flours` - baker's percentages of the blend relative to each other; they
  don't need to sum to exactly 100, they're normalized (with a warning) if not. Every
  `pizza_flours_id` must match an entry in the flour catalogue (see below) - its `id` or
  one of its localized names/codes; anything else is rejected with a 400. `ash%` is
  optional and only meaningful for milled wheat flours (e.g. `0.55` for Italian Tipo 00,
  per DPR 187/2001) - when set, it's cross-checked against the resolved flour's ash
  range and a mismatch is returned as a (non-fatal) warning rather than rejected.
  `description` is an optional free-text note for the specific brand/product used (e.g.
  `"Semola Caputo"`) - purely informational, not matched against the catalogue.
- `pre_ferment` - optional; omit entirely for a plain commercial-yeast dough. When set,
  it builds ONE aggregate preferment from a reusable blend - named components (e.g.
  "biga 60% / poolish 40%") are descriptive/echoed metadata only, never computed
  separately (a single preferment mass, not two separately-computed ones):
  - `type_id` - references a blend saved via `POST /pre-ferment-types` (see below), e.g.
    `"biga60_poolish40"`. Required.
  - `percentage` - the preferment's baker's % of total flour weight (grams of preferment
    flour per 100g of total flour, e.g. the baguette formula's "Poolish 400g / 40%");
    defaults to 40 when omitted.
- Any of `hydration_pct`, `salt_pct`, `oil_pct`, `yeast_pct`, `ball_weight_g` left unset
  falls back to a generic baker's-percentage default (62% hydration, 2.5% salt, 0% oil,
  250g ball weight).

The response echoes `ingredients.flours` back with `grams` added, and `pre_ferment`
back with the actually-used percentage (override or default) and resolved components -
`null` when no pre-ferment was set. It also includes the leavening breakdown (commercial
yeast %, or an aggregate preferment split with its `percent_of_flour`) - scaled to
`num_balls` - plus `ingredients_per_ball` (a constant single-ball reference, regardless
of `num_balls`, **not** to be confused with `ingredients.flours` - different things that
happen to share a name prefix), `ingredients_total` (the full batch), and a step-by-step
fermentation schedule.

### Pre-ferment types (Postgres-only)

`pre_ferment_types` is a small reference table of reusable named blends a recipe's
`pre_ferment.type_id` points at - e.g. save `biga80_sourdough20` once (biga 80% /
sourdough 20%), then reuse it across recipes. It's **only available when
`DB_BACKEND=postgres`**; the other endpoints (`/recipes/*`) work on any backend
regardless. On sqlite/cosmos, `/pre-ferment-types` requests return `400` explaining that
Postgres is required.

```json
// POST /pre-ferment-types
{"type_id": "biga80_sourdough20", "preferments": [{"name": "biga", "percentage": 80}, {"name": "sourdough", "percentage": 20}]}
```

A row is deliberately just `type_id` + `preferments` (name/percentage pairs) - no
technique, hydration, or resting-hours columns; those stay recipe-level concerns.

### International flour catalogue

Every `ingredients.flours[].pizza_flours_id` cited in a request must match an entry from
`GET /recipes/flours` - matched case-insensitively against that entry's `id` or any of
its localized names/codes, so you can use whatever your country calls it: `"00"`,
`"Farina 00"`, `"Weizenmehl 405"`, and `"T45"` all resolve to the same `soft_wheat_00`
flour. The catalogue covers wheat (soft wheat types 00/0/1/2, whole wheat, Manitoba,
durum, Italian ancient-grain landraces), rye, oats, gluten-free cereals (rice, corn,
millet, sorghum, teff, ...), legumes, nuts/seeds, tubers/starches, and a few specialty
flours - ~60 entries in total, each with `id`, `category`, `gluten`, `bread`/`pizza`
suitability, `max_blend_pct`, and localized `names` (en/it/fr/de). Each entry also
carries `pizza_flours_id` (mirrors `id`) and `description` (mirrors `notes` where an
entry has one, else unset) - the same field names used on a recipe request's
`ingredients.flours[]`, though there they mean something request-specific:
`pizza_flours_id` is the caller's lookup key, and `description` is a free-text
brand/product note.

Entries for milled wheat refinement grades (the soft-wheat 00/0/1/2/whole-wheat ladder,
rye, spelt) also carry `ash_min_pct`/`ash_max_pct` - the ash content (% per 100g of
flour) that grade corresponds to, per the Italian DPR 187/2001, German DIN 10355, and
French Calvel classifications. Italian Tipo 00 is ash ≤0.55%, Tipo 0 ≤0.65%, Tipo 1
≤0.80%, Tipo 2 ≤0.95% (semi-integrale), and integrale 1.30-1.70% (that last one is the
narrower legal band; the catalogue's `whole_wheat` range, 1.20-1.80%, is the broader
cross-country correspondence band `WHEAT_CLASSIFICATIONS` in `app/flours.py` derives
from). Other flours (durum, ancient wheats, rice, legumes, starches, ...) have no ash
field. A request's `flours[].ash%` is cross-checked against this range when both are
present.

This catalogue is seed data (`app/flours.py`'s `FLOUR_CATALOG`). When `DB_BACKEND=cosmos`,
it lives in its own Cosmos container (`COSMOS_FLOURS_CONTAINER`, default `pizza_flours`)
instead of hardcoded in the source, seeded automatically the first time that container
is empty. Non-Cosmos backends (`sqlite`/`postgres`, and the test suite) serve the seed
data directly from memory. **A container seeded before the ash fields existed won't pick
them up on its own** (seeding only runs against an empty container) - run
`python scripts/backfill_flour_ash.py` against it once to patch `ash_min_pct`/
`ash_max_pct` into the existing documents in place, or delete the container and let the
app recreate/reseed it from scratch (see below).

The `pizza_recipes`/`pizza_flours` containers (and their non-Cosmos equivalents) are
built eagerly in `app/main.py`'s startup hook, not lazily on first request - so a deploy
alone is what creates/reseeds them (e.g. if a container was deleted out-of-band),
without needing a request to hit a specific endpoint first.

## Configuration

Copy `.env.example` to `.env` and adjust. Key setting: `DB_BACKEND`:

- `sqlite` (default) - zero-config local file DB, good for quick local runs.
- `postgres` - any Postgres-wire-compatible database, including a **Render**
  [managed Postgres](https://render.com/pricing#postgresql) instance - just set
  `POSTGRES_URL` to Render's external connection string. Required for
  `/pre-ferment-types` (see above) - that table is Postgres-only, unlike everything else.
- `cosmos` - **Azure Cosmos DB** (NoSQL API) - set `COSMOS_ENDPOINT` and `COSMOS_KEY`
  from an existing Cosmos account; `COSMOS_DATABASE`/`COSMOS_CONTAINER` are
  auto-created if missing.

`ANTHROPIC_API_KEY` enables `/agent/chat`; without it the endpoint returns a message
saying the key is missing instead of erroring.

## Run locally

```bash
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Run with Docker

```bash
docker compose up --build
# or, with a local Postgres too:
docker compose --profile postgres up --build
```

## Deploy to Render

This folder ships a `render.yaml` [Blueprint](https://render.com/docs/blueprint-spec) that
deploys the web service (built from the included `Dockerfile`) against **Azure Cosmos
DB**. Render doesn't host Cosmos DB itself (it's an Azure service), so you provision the
Cosmos account in Azure first and just point the Render service at it.

### 1. Create the Cosmos DB account (Azure Portal)

1. In the [Azure Portal](https://portal.azure.com), create an **Azure Cosmos DB**
   resource and pick the **NoSQL** API (not MongoDB/Cassandra/etc.) - the service uses
   the `azure-cosmos` SDK, which speaks the NoSQL API. The free tier (1000 RU/s +
   25GB) is enough for this service.
2. Once it's provisioned, open **Settings -> Keys** on the Cosmos account and copy:
   - **URI** -> this is `COSMOS_ENDPOINT`
   - **PRIMARY KEY** -> this is `COSMOS_KEY`
3. You don't need to pre-create the database/container - the service calls
   `create_database_if_not_exists` / `create_container_if_not_exists` on startup using
   `COSMOS_DATABASE` (default `ai-agent`) and `COSMOS_CONTAINER` (default
   `pizza_recipes`).

### 2. Deploy on Render

1. Push this repo to GitHub (already the case if you're reading this in the repo).
2. In the Render dashboard: **New -> Blueprint**, and point it at this repo. It reads
   `render.yaml` and creates the `pizza-service` web service with `DB_BACKEND=cosmos`
   pre-set.
3. After the first deploy, open the service's **Environment** tab and set the values
   left blank in the blueprint on purpose (they're secrets):
   - `COSMOS_ENDPOINT`, `COSMOS_KEY` - from step 1
   - `API_KEY` - your own value, to require `X-API-Key` on mutating requests
   - `ANTHROPIC_API_KEY` - to enable `/agent/chat`
4. Render calls `GET /health` for its health check; the service is live at
   `https://<service-name>.onrender.com` once that passes and redeploys after you save
   the env vars.

Prefer Render's own managed Postgres instead of Cosmos? Switch `DB_BACKEND` back to
`postgres` and see the commented-out block at the bottom of `render.yaml` for the
`databases:` section to add back.

You can also skip the blueprint and create the web service manually (Docker runtime)
and point `DB_BACKEND=sqlite` at it for a no-database quick deploy - recipes just
won't survive a redeploy/restart in that mode.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
