import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.recipe import DEFAULT_HYDRATION_PCT, compute_recipe, scale_recipe

client = TestClient(app)

# Valid catalogue flour types (see app/flours.py) used across API-level tests, which
# validate ingredients.flours[].pizza_flours_id against the flour catalogue.
SOFT_WHEAT_00 = "soft_wheat_00"
WHOLE_WHEAT = "whole_wheat"

BIGA_POOLISH = {"components": [{"name": "biga", "percentage": 60}, {"name": "poolish", "percentage": 40}], "percentage": 40}


def test_compute_recipe_is_a_single_ball_baseline():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 80}, {"type": "Whole wheat", "percent": 20}],
        ball_weight_g=250,
    )
    assert "num_balls" not in result
    assert "total_dough_g" not in result
    per_ball = result["ingredients_per_ball"]
    dough_sum = per_ball["flour_g"] + per_ball["water_g"] + per_ball["salt_g"] + per_ball["oil_g"]
    assert dough_sum == pytest.approx(250.0, rel=0.01)
    assert sum(f["percent"] for f in result["ingredients"]["flours"]) == pytest.approx(100.0)
    assert result["leavening"]["type"] == "instant dry yeast"
    assert result["pre_ferment"] is None


def test_scale_recipe_expands_to_a_batch():
    base = compute_recipe(flours=[{"type": "00 flour", "percent": 100}], ball_weight_g=250)
    scaled = scale_recipe(base, 4)
    assert scaled["num_balls"] == 4
    assert scaled["total_dough_g"] == pytest.approx(1000.0)
    assert scaled["ingredients_total"]["flour_g"] == pytest.approx(base["ingredients_per_ball"]["flour_g"] * 4, abs=0.1)
    # per-ball reference stays the same regardless of batch size
    assert scaled["ingredients_per_ball"] == base["ingredients_per_ball"]
    # percentages/schedule are unaffected by batch size
    assert scaled["ingredients"]["flours"][0]["percent"] == base["ingredients"]["flours"][0]["percent"]
    assert scaled["ingredients"]["flours"][0]["grams"] == pytest.approx(base["ingredients"]["flours"][0]["grams"] * 4, abs=0.1)
    assert scaled["fermentation_schedule"] == base["fermentation_schedule"]


def test_scale_recipe_scales_preferment_leavening_grams():
    base = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}], pre_ferment=BIGA_POOLISH,
        hydration_pct=65, ball_weight_g=280,
    )
    scaled = scale_recipe(base, 3)
    assert scaled["leavening"]["preferment_flour_g"] == pytest.approx(base["leavening"]["preferment_flour_g"] * 3, abs=0.1)
    assert scaled["leavening"]["rest_hours"] == base["leavening"]["rest_hours"]  # text, unaffected
    assert scaled["leavening"]["components"] == base["leavening"]["components"]  # metadata, unaffected


def test_scale_recipe_rejects_non_positive_num_balls():
    base = compute_recipe(flours=[{"type": "00 flour", "percent": 100}])
    with pytest.raises(ValueError):
        scale_recipe(base, 0)


def test_flour_percentages_are_normalized_with_warning():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 70}, {"type": "Semola", "percent": 50}],
        ball_weight_g=250,
    )
    assert sum(f["percent"] for f in result["ingredients"]["flours"]) == pytest.approx(100.0)
    assert any("normalized" in w for w in result["warnings"])


def test_defaults_apply_when_unset():
    result = compute_recipe(flours=[{"type": "00 flour", "percent": 100}])
    assert result["hydration_pct"] == DEFAULT_HYDRATION_PCT


def test_pre_ferment_builds_a_preferment_with_default_percentage():
    result = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}],
        pre_ferment={"components": [{"name": "poolish", "percentage": 100}], "percentage": 40},
        hydration_pct=65,
        ball_weight_g=280,
    )
    assert result["leavening"]["type"] == "preferment"
    assert result["leavening"]["preferment_flour_g"] > 0
    assert result["leavening"]["percent_of_flour"] == 40.0
    assert result["pre_ferment"] == {"components": [{"name": "poolish", "percentage": 100}], "percentage": 40.0}


def test_pre_ferment_with_multiple_named_components_is_not_split_per_component():
    result = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 65}, {"type": "00 flour", "percent": 35}],
        pre_ferment=BIGA_POOLISH,
        hydration_pct=76,
        ball_weight_g=1000,
    )
    leavening = result["leavening"]
    assert leavening["percent_of_flour"] == 40
    assert leavening["components"] == BIGA_POOLISH["components"]
    # one aggregate preferment mass, not one per component
    assert leavening["preferment_flour_g"] == pytest.approx(
        result["ingredients_per_ball"]["flour_g"] * 0.40, abs=0.1
    )
    assert result["pre_ferment"] == {"components": BIGA_POOLISH["components"], "percentage": 40}


def test_pre_ferment_percentage_overrides_the_default():
    result = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}],
        pre_ferment={"components": [{"name": "biga", "percentage": 100}], "percentage": 55},
        hydration_pct=65,
        ball_weight_g=280,
    )
    assert result["leavening"]["percent_of_flour"] == 55
    assert result["pre_ferment"]["percentage"] == 55


def test_no_pre_ferment_reports_none():
    result = compute_recipe(flours=[{"type": "00 flour", "percent": 100}])
    assert result["pre_ferment"] is None
    assert result["leavening"]["type"] == "instant dry yeast"


def test_api_generate_endpoint():
    response = client.post(
        "/recipes/generate",
        params={"num_balls": 3},
        json={
            "ingredients": {
                "flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 90}, {"pizza_flours_id": WHOLE_WHEAT, "percent": 10}],
            },
            "hydration_pct": 63,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["num_balls"] == 3
    assert body["ingredients_per_ball"]["flour_g"] == pytest.approx(body["ingredients_total"]["flour_g"] / 3, abs=0.1)
    assert body["hydration_pct"] == 63


def test_api_generate_passes_through_brand_description():
    response = client.post(
        "/recipes/generate",
        json={
            "ingredients": {
                "flours": [
                    {"pizza_flours_id": "durum_semolina", "description": "Semola Caputo", "percent": 70},
                    {"pizza_flours_id": SOFT_WHEAT_00, "description": "Naturaplan Bio CH Weissmehl Coop", "percent": 30},
                ],
            },
        },
    )
    assert response.status_code == 200
    flours = {f["pizza_flours_id"]: f for f in response.json()["ingredients"]["flours"]}
    assert flours["durum_semolina"]["description"] == "Semola Caputo"
    assert flours[SOFT_WHEAT_00]["description"] == "Naturaplan Bio CH Weissmehl Coop"


def test_api_generate_omits_description_when_unset():
    response = client.post(
        "/recipes/generate",
        json={"ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]}},
    )
    assert response.status_code == 200
    assert response.json()["ingredients"]["flours"][0]["description"] is None


def test_api_generate_defaults_to_one_ball():
    response = client.post(
        "/recipes/generate",
        json={"ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["num_balls"] == 1
    assert body["total_dough_g"] == pytest.approx(body["ball_weight_g"])


def test_api_generate_defaults_to_no_pre_ferment_when_omitted():
    response = client.post(
        "/recipes/generate",
        json={"ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]}},
    )
    assert response.status_code == 200
    assert response.json()["pre_ferment"] is None


def test_api_generate_accepts_multiple_named_pre_ferment_components():
    response = client.post(
        "/recipes/generate",
        json={
            "ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]},
            "pre_ferment": {
                "components": [{"name": "biga", "percentage": 60}, {"name": "poolish", "percentage": 40}],
                "percentage": 35,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pre_ferment"]["components"] == [{"name": "biga", "percentage": 60}, {"name": "poolish", "percentage": 40}]
    assert body["leavening"]["percent_of_flour"] == 35


def test_api_generate_rejects_components_not_summing_to_100():
    response = client.post(
        "/recipes/generate",
        json={
            "ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]},
            "pre_ferment": {"components": [{"name": "biga", "percentage": 60}, {"name": "poolish", "percentage": 30}]},
        },
    )
    assert response.status_code == 422


def test_api_generate_rejects_setting_both_type_id_and_components():
    response = client.post(
        "/recipes/generate",
        json={
            "ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]},
            "pre_ferment": {"type_id": "biga100", "components": [{"name": "biga", "percentage": 100}]},
        },
    )
    assert response.status_code == 422


def test_api_generate_rejects_setting_neither_type_id_nor_components():
    response = client.post(
        "/recipes/generate",
        json={
            "ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]},
            "pre_ferment": {"percentage": 40},
        },
    )
    assert response.status_code == 422


def test_api_generate_rejects_unknown_pre_ferment_type_id():
    response = client.post(
        "/recipes/generate",
        json={
            "ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]},
            "pre_ferment": {"type_id": "does_not_exist"},
        },
    )
    assert response.status_code == 400


def test_api_save_list_get_delete_roundtrip():
    create = client.post(
        "/recipes",
        json={
            "name": "Friday night pizza",
            "ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]},
        },
    )
    assert create.status_code == 200
    body = create.json()
    assert body["num_balls"] == 1  # saved response defaults to a single-ball view
    item_id = body["id"]

    listing = client.get("/recipes")
    assert listing.status_code == 200
    assert listing.json()["count"] >= 1

    fetched = client.get(f"/recipes/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Friday night pizza"

    scaled = client.get(f"/recipes/{item_id}", params={"num_balls": 5})
    assert scaled.status_code == 200
    scaled_body = scaled.json()
    assert scaled_body["num_balls"] == 5
    assert scaled_body["total_dough_g"] == pytest.approx(scaled_body["ball_weight_g"] * 5)
    assert scaled_body["ingredients_per_ball"] == fetched.json()["ingredients_per_ball"]

    deleted = client.delete(f"/recipes/{item_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/recipes/{item_id}")
    assert missing.status_code == 404


def test_api_save_recipe_without_a_name_defaults_from_pre_ferment():
    response = client.post(
        "/recipes",
        json={"ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}]}},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Direct dough"


def test_api_rejects_unknown_flour():
    response = client.post(
        "/recipes/generate",
        json={"ingredients": {"flours": [{"pizza_flours_id": "moon dust", "percent": 100}]}},
    )
    assert response.status_code == 400
    assert "unknown flour type" in response.json()["detail"]


def test_api_flours_endpoint_lists_catalog():
    response = client.get("/recipes/flours")
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()["items"]}
    assert SOFT_WHEAT_00 in ids
    assert "rice_white" in ids
    assert "durum_rimacinata" in ids


def test_api_flours_endpoint_exposes_ash_content():
    response = client.get("/recipes/flours")
    items = {f["id"]: f for f in response.json()["items"]}
    assert items[SOFT_WHEAT_00]["ash_min_pct"] == 0.00
    assert items[SOFT_WHEAT_00]["ash_max_pct"] == 0.55
    assert items["rice_white"].get("ash_min_pct") is None


def test_api_generate_accepts_matching_ash_pct_without_warning():
    response = client.post(
        "/recipes/generate",
        json={"ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "ash%": 0.50, "percent": 100}]}},
    )
    assert response.status_code == 200
    assert not any("ash%" in w for w in response.json()["warnings"])


def test_api_generate_warns_on_mismatched_ash_pct():
    response = client.post(
        "/recipes/generate",
        json={"ingredients": {"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "ash%": 1.50, "percent": 100}]}},
    )
    assert response.status_code == 200
    assert any("ash%" in w for w in response.json()["warnings"])
