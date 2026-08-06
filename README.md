# Pizza Service (AI Agent)

FastAPI microservice that turns a **flour blend** (baker's percentages), a **fermentation
technique**, and an optional **named style** (each anchored to a real pizza-chef/cookbook
reference) into a scaled pizza dough recipe: ingredient weights, a preferment/starter
breakdown where relevant, and a fermentation schedule. Also exposes a built-in AI agent
endpoint (`/agent/chat`) that can do the same from a natural-language instruction via
Anthropic tool-calling.

Extracted from the [`ict_project`](https://github.com/marcomaggiotti/ict_project) monorepo
as a standalone, self-contained service (own dependencies, Dockerfile, config).

## Endpoints

| Method | Path              | Description                                                |
|--------|-------------------|--------------------------------------------------------------|
| GET    | `/health`         | Liveness check                                                |
| GET    | `/recipes/styles` | List the built-in named styles and their chef/book attribution |
| POST   | `/recipes/generate` | Compute a recipe without saving it                           |
| POST   | `/recipes`        | Compute a recipe and save it                                  |
| GET    | `/recipes`        | List saved recipes (`limit`, `offset`)                        |
| GET    | `/recipes/{id}`   | Get one saved recipe                                          |
| DELETE | `/recipes/{id}`   | Delete a saved recipe                                          |
| POST   | `/agent/chat`     | Natural-language agent chat over recipe generation/storage    |

All endpoints except `/health` require header `X-API-Key` if `API_KEY` is set in the
environment; leave it empty for local dev.

## The recipe model

Request body for `/recipes/generate` and `/recipes`:

```json
{
  "name": "Friday pizza night",
  "flours": [
    {"type": "Italian 00 flour", "percent": 80},
    {"type": "Whole wheat", "percent": 20}
  ],
  "technique": "cold_ferment_48h",
  "style": "ny_style",
  "hydration_pct": 63,
  "salt_pct": 2.5,
  "oil_pct": 3,
  "num_balls": 4,
  "ball_weight_g": 280
}
```

- `flours` - baker's percentages of the blend relative to each other; they don't need to
  sum to exactly 100, they're normalized (with a warning) if not.
- `technique` - one of `direct`, `same_day`, `poolish`, `biga`, `sourdough`,
  `cold_ferment_24h`, `cold_ferment_48h`, `cold_ferment_72h`. Drives the yeast/preferment
  math and the generated fermentation schedule.
- `style` - optional named style key (see `GET /recipes/styles`, or below). Supplies
  defaults for anything left unset (`hydration_pct`, `salt_pct`, `oil_pct`,
  `ball_weight_g`) and carries the recipe's book/author attribution. Defaults to
  `custom` (generic defaults, no attribution).
- Any of `hydration_pct`, `salt_pct`, `oil_pct`, `yeast_pct`, `ball_weight_g` you *do*
  set overrides the style default.

The response includes the normalized flour blend with grams, total dough/per-ball
ingredient weights, the leavening breakdown (commercial yeast %, or a poolish/biga
preferment split, or a sourdough starter %), a step-by-step fermentation schedule, and
the style's attribution.

### Built-in styles (pizza-chef / cookbook references)

| Key | Style | Author | Book / reference |
|-----|-------|--------|-------------------|
| `neapolitan_avpn` | Neapolitan | Associazione Verace Pizza Napoletana (AVPN) | AVPN Disciplinare |
| `ny_style` | New York style | Tony Gemignani | The Pizza Bible |
| `detroit_style` | Detroit style (pan) | Ken Forkish | The Elements of Pizza |
| `roman_al_taglio` | Roman-style al taglio | Gabriele Bonci | Pizza: Seasonal Recipes from Rome's Legendary Pizzarium |
| `sourdough_fwsy` | Naturally leavened | Ken Forkish | Flour Water Salt Yeast |
| `american_pie_reinhart` | American artisan | Peter Reinhart | American Pie: My Search for the Perfect Pizza |
| `modernist_pizza` | Precision baker's-% formula | Nathan Myhrvold et al. | Modernist Pizza |
| `custom` | Custom formulation | - | - (generic defaults, override freely) |

## Configuration

Copy `.env.example` to `.env` and adjust. Key setting: `DB_BACKEND`:

- `sqlite` (default) - zero-config local file DB, good for quick local runs.
- `postgres` - any Postgres-wire-compatible database, including a **Render**
  [managed Postgres](https://render.com/pricing#postgresql) instance - just set
  `POSTGRES_URL` to Render's external connection string.
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
