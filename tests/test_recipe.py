import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.recipe import STYLE_LIBRARY, TECHNIQUES, compute_recipe

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
    assert body["num_balls"] == 3
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
    keys = {s["key"] for s in response.json()}
    assert keys == set(STYLE_LIBRARY)


def test_api_rejects_bad_technique():
    response = client.post(
        "/recipes/generate",
        json={"flours": [{"type": "00 flour", "percent": 100}], "technique": "invalid"},
    )
    assert response.status_code == 422
