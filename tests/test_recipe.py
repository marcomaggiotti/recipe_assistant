import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.recipe import STYLE_LIBRARY, TECHNIQUES, compute_recipe
from app.schemas import GeneratedRecipe, StyleAttribution, StyleInfo

client = TestClient(app)


def test_compute_recipe_direct_matches_ball_count_and_weight():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 80}, {"type": "Whole wheat", "percent": 20}],
        technique="direct",
        style="custom",
        num_balls=4,
        ball_weight_g=250,
    )
    assert result["total_dough_g"] == pytest.approx(1000.0)
    total = result["ingredients_total"]
    dough_sum = total["flour_g"] + total["water_g"] + total["salt_g"] + total["oil_g"]
    assert dough_sum == pytest.approx(1000.0, rel=0.01)
    assert sum(f["percent"] for f in result["flours"]) == pytest.approx(100.0)
    assert result["leavening"]["type"] == "instant dry yeast"


def test_flour_percentages_are_normalized_with_warning():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 70}, {"type": "Semola", "percent": 50}],
        technique="direct",
        num_balls=1,
        ball_weight_g=250,
    )
    assert sum(f["percent"] for f in result["flours"]) == pytest.approx(100.0)
    assert any("normalized" in w for w in result["warnings"])


def test_style_defaults_apply_when_unset():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 100}],
        technique="direct",
        style="neapolitan_avpn",
    )
    style = STYLE_LIBRARY["neapolitan_avpn"]
    assert result["hydration_pct"] == style["hydration_pct"]
    assert result["style_attribution"]["author"] == style["author"]
    assert result["style_attribution"]["book"] == style["book"]


def test_preferment_techniques_build_a_preferment():
    for technique in ("poolish", "biga"):
        result = compute_recipe(
            flours=[{"type": "Bread flour", "percent": 100}],
            technique=technique,
            hydration_pct=65,
            num_balls=2,
            ball_weight_g=280,
        )
        assert result["leavening"]["type"] == technique
        assert result["leavening"]["preferment_flour_g"] > 0


def test_unknown_technique_rejected():
    with pytest.raises(ValueError):
        compute_recipe(flours=[{"type": "00 flour", "percent": 100}], technique="bogus")


def test_explicit_style_defaults_override_style_library():
    custom_style = {
        "label": "Injected style", "author": "Someone", "book": "Some Book",
        "hydration_pct": 70.0, "salt_pct": 3.0, "oil_pct": 0.0,
        "technique": "direct", "ball_weight_g": 260.0,
        "suggested_flours": [], "notes": "from an external store",
    }
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 100}],
        technique="direct",
        style="not_in_style_library",
        style_defaults=custom_style,
    )
    assert result["hydration_pct"] == 70.0
    assert result["style"] == "not_in_style_library"
    assert result["style_attribution"]["author"] == "Someone"


def test_all_styles_generate_without_error():
    for style in STYLE_LIBRARY:
        result = compute_recipe(
            flours=[{"type": "00 flour", "percent": 100}],
            technique=STYLE_LIBRARY[style]["technique"],
            style=style,
        )
        assert result["style"] == style


def test_api_generate_endpoint():
    response = client.post(
        "/recipes/generate",
        json={
            "flours": [{"type": "00 flour", "percent": 90}, {"type": "Whole wheat", "percent": 10}],
            "technique": "cold_ferment_48h",
            "style": "ny_style",
            "num_balls": 3,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "num_balls" not in body
    assert body["ingredients_per_ball"]["flour_g"] == pytest.approx(body["ingredients_total"]["flour_g"] / 3, abs=0.1)
    assert body["style_attribution"]["author"] == "Tony Gemignani"


def test_api_save_list_get_delete_roundtrip():
    create = client.post(
        "/recipes",
        json={
            "name": "Friday night pizza",
            "flours": [{"type": "00 flour", "percent": 100}],
            "technique": "direct",
        },
    )
    assert create.status_code == 200
    item_id = create.json()["id"]

    listing = client.get("/recipes")
    assert listing.status_code == 200
    assert listing.json()["count"] >= 1

    fetched = client.get(f"/recipes/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Friday night pizza"

    deleted = client.delete(f"/recipes/{item_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/recipes/{item_id}")
    assert missing.status_code == 404


def test_api_styles_endpoint_lists_all():
    response = client.get("/recipes/styles")
    assert response.status_code == 200
    body = response.json()
    keys = {s["style"] for s in body}
    assert keys == set(STYLE_LIBRARY)
    sample = next(s for s in body if s["style"] == "neapolitan_avpn")
    assert sample["style_attribution"]["author"] == "Associazione Verace Pizza Napoletana (AVPN)"


def test_style_info_shares_field_names_with_generated_recipe():
    # StyleInfo should use the same "style"/"style_attribution" naming and the same
    # recipe-default field names (technique, hydration_pct, ...) as GeneratedRecipe,
    # rather than a flattened/renamed ("key" instead of "style") shape of its own.
    shared_fields = {"style", "technique", "hydration_pct", "salt_pct", "oil_pct", "ball_weight_g", "style_attribution"}
    assert shared_fields <= set(StyleInfo.model_fields)
    assert shared_fields <= set(GeneratedRecipe.model_fields)
    assert StyleInfo.model_fields["style_attribution"].annotation is StyleAttribution
    assert GeneratedRecipe.model_fields["style_attribution"].annotation is StyleAttribution


def test_api_rejects_bad_technique():
    response = client.post(
        "/recipes/generate",
        json={"flours": [{"type": "00 flour", "percent": 100}], "technique": "invalid"},
    )
    assert response.status_code == 422


def test_api_rejects_unknown_style():
    response = client.post(
        "/recipes/generate",
        json={
            "flours": [{"type": "00 flour", "percent": 100}],
            "technique": "direct",
            "style": "does_not_exist",
        },
    )
    assert response.status_code == 400
