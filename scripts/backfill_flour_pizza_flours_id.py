"""One-off migration: patch pizza_flours_id/description into an already-seeded Azure
Cosmos "pizza_flours" container.

app/flours.py's CosmosFlourCatalogStore only seeds FLOUR_CATALOG into Cosmos the first
time the container is empty - a container seeded before these two fields existed keeps
its old documents untouched. This script patches the same values used by the in-code
seed data (see app/flours.py) into the live container's existing documents: for each
flour id, pizza_flours_id is set to that same id, and description is set to whatever
FLOUR_CATALOG derives it from (its notes field, or unset).

Usage (against the environment whose Cosmos account you want to update):
    DB_BACKEND=cosmos COSMOS_ENDPOINT=... COSMOS_KEY=... python scripts/backfill_flour_pizza_flours_id.py
Reads the same COSMOS_* settings as the running service (.env or the process
environment) via app.config.Settings, so point it at prod by pointing .env at prod.
"""
from azure.cosmos import CosmosClient

from app.config import get_settings
from app.flours import FLOUR_CATALOG


def main() -> None:
    settings = get_settings()
    if not settings.cosmos_endpoint or not settings.cosmos_key:
        raise SystemExit("COSMOS_ENDPOINT/COSMOS_KEY are not set - point .env at the target Cosmos account first")

    client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
    container = (
        client.get_database_client(settings.cosmos_database)
        .get_container_client(settings.cosmos_flours_container)
    )

    patched, missing = 0, []
    for flour in FLOUR_CATALOG:
        flour_id = flour["id"]
        try:
            doc = container.read_item(item=flour_id, partition_key=flour_id)
        except Exception:
            missing.append(flour_id)
            continue
        doc["pizza_flours_id"] = flour["pizza_flours_id"]
        doc["description"] = flour["description"]
        container.upsert_item(doc)
        patched += 1

    print(f"Patched {patched} document(s) with pizza_flours_id/description.")
    if missing:
        print(f"Skipped (not found in container): {', '.join(missing)}")


if __name__ == "__main__":
    main()
