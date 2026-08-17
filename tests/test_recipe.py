import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.recipe import STYLE_LIBRARY, TECHNIQUES, compute_recipe, scale_recipe
from app.schemas import GeneratedRecipe, StyleAttribution, StyleInfo

client = TestClient(app)

# Valid catalogue flour types (see app/flours.py) used across API-level tests, which
# validate flours[].pizza_flours_id against the flour catalogue.
SOFT_WHEAT_00 = "soft_wheat_00"
WHOLE_WHEAT = "whole_wheat"


def test_compute_recipe_is_a_single_ball_baseline():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 80}, {"type": "Whole wheat", "percent": 20}],
        technique="direct",
        style="custom",
        ball_weight_g=250,
    )
    assert "num_balls" not in result
    assert "total_dough_g" not in result
    per_ball = result["ingredients_per_ball"]
    dough_sum = per_ball["flour_g"] + per_ball["water_g"] + per_ball["salt_g"] + per_ball["oil_g"]
    assert dough_sum == pytest.approx(250.0, rel=0.01)
    assert sum(f["percent"] for f in result["flours"]) == pytest.approx(100.0)
    assert result["leavening"]["type"] == "instant dry yeast"


def test_scale_recipe_expands_to_a_batch():
    base = compute_recipe(
        flours=[{"type": "00 flour", "percent": 100}], technique="direct", ball_weight_g=250,
    )
    scaled = scale_recipe(base, 4)
    assert scaled["num_balls"] == 4
    assert scaled["total_dough_g"] == pytest.approx(1000.0)
    assert scaled["ingredients_total"]["flour_g"] == pytest.approx(base["ingredients_per_ball"]["flour_g"] * 4, abs=0.1)
    # per-ball reference stays the same regardless of batch size
    assert scaled["ingredients_per_ball"] == base["ingredients_per_ball"]
    # percentages/technique/schedule/attribution are unaffected by batch size
    assert scaled["flours"][0]["percent"] == base["flours"][0]["percent"]
    assert scaled["flours"][0]["grams"] == pytest.approx(base["flours"][0]["grams"] * 4, abs=0.1)
    assert scaled["fermentation_schedule"] == base["fermentation_schedule"]


def test_scale_recipe_scales_preferment_leavening_grams():
    base = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}], technique="poolish",
        hydration_pct=65, ball_weight_g=280,
    )
    scaled = scale_recipe(base, 3)
    assert scaled["leavening"]["preferment_flour_g"] == pytest.approx(base["leavening"]["preferment_flour_g"] * 3, abs=0.1)
    assert scaled["leavening"]["rest_hours"] == base["leavening"]["rest_hours"]  # text, unaffected


def test_scale_recipe_rejects_non_positive_num_balls():
    base = compute_recipe(flours=[{"type": "00 flour", "percent": 100}], technique="direct")
    with pytest.raises(ValueError):
        scale_recipe(base, 0)


def test_flour_percentages_are_normalized_with_warning():
    result = compute_recipe(
        flours=[{"type": "00 flour", "percent": 70}, {"type": "Semola", "percent": 50}],
        technique="direct",
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
            ball_weight_g=280,
        )
        assert result["leavening"]["type"] == technique
        assert result["leavening"]["preferment_flour_g"] > 0
        assert result["leavening"]["percent_of_flour"] == 40.0  # default when unset


def test_poolish_percentage_overrides_the_default_and_scales_preferment_flour():
    result = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 65}, {"type": "00 flour", "percent": 35}],
        technique="poolish",
        poolish_percentage=40,
        hydration_pct=76,
        ball_weight_g=1000,
    )
    leavening = result["leavening"]
    assert leavening["percent_of_flour"] == 40
    assert leavening["preferment_flour_g"] == pytest.approx(
        result["ingredients_per_ball"]["flour_g"] * 0.40, abs=0.1
    )
    # biga_percentage/sourdough_percentage don't apply to a poolish recipe
    other = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}],
        technique="poolish",
        biga_percentage=70,
        sourdough_percentage=10,
        hydration_pct=65,
        ball_weight_g=280,
    )
    assert other["leavening"]["percent_of_flour"] == 40.0


def test_biga_percentage_overrides_the_default():
    result = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}],
        technique="biga",
        biga_percentage=55,
        hydration_pct=65,
        ball_weight_g=280,
    )
    assert result["leavening"]["percent_of_flour"] == 55


def test_sourdough_percentage_overrides_the_default():
    result = compute_recipe(
        flours=[{"type": "Bread flour", "percent": 100}],
        technique="sourdough",
        sourdough_percentage=25,
        hydration_pct=68,
        ball_weight_g=260,
    )
    assert result["leavening"]["percent_of_flour"] == 25
    assert result["leavening"]["grams"] == pytest.approx(
        result["ingredients_per_ball"]["flour_g"] * 0.25, abs=0.1
    )


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
        params={"num_balls": 3},
        json={
            "flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 90}, {"pizza_flours_id": WHOLE_WHEAT, "percent": 10}],
            "technique": "cold_ferment_48h",
            "style": "ny_style",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["num_balls"] == 3
    assert body["ingredients_per_ball"]["flour_g"] == pytest.approx(body["ingredients_total"]["flour_g"] / 3, abs=0.1)
    assert body["style_attribution"]["author"] == "Tony Gemignani"


def test_api_generate_passes_through_brand_description():
    response = client.post(
        "/recipes/generate",
        json={
            "flours": [
                {"pizza_flours_id": "durum_semolina", "description": "Semola Caputo", "percent": 70},
                {"pizza_flours_id": SOFT_WHEAT_00, "description": "Naturaplan Bio CH Weissmehl Coop", "percent": 30},
            ],
            "technique": "direct",
        },
    )
    assert response.status_code == 200
    flours = {f["pizza_flours_id"]: f for f in response.json()["flours"]}
    assert flours["durum_semolina"]["description"] == "Semola Caputo"
    assert flours[SOFT_WHEAT_00]["description"] == "Naturaplan Bio CH Weissmehl Coop"


def test_api_generate_omits_description_when_unset():
    response = client.post(
        "/recipes/generate",
        json={"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}], "technique": "direct"},
    )
    assert response.status_code == 200
    assert response.json()["flours"][0]["description"] is None


def test_api_generate_defaults_to_one_ball():
    response = client.post(
        "/recipes/generate",
        json={"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}], "technique": "direct"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["num_balls"] == 1
    assert body["total_dough_g"] == pytest.approx(body["ball_weight_g"])


def test_api_save_list_get_delete_roundtrip():
    create = client.post(
        "/recipes",
        json={
            "name": "Friday night pizza",
            "flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}],
            "technique": "direct",
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
        json={"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}], "technique": "invalid"},
    )
    assert response.status_code == 422


def test_api_rejects_unknown_style():
    response = client.post(
        "/recipes/generate",
        json={
            "flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}],
            "technique": "direct",
            "style": "does_not_exist",
        },
    )
    assert response.status_code == 400


def test_api_rejects_unknown_flour():
    response = client.post(
        "/recipes/generate",
        json={"flours": [{"pizza_flours_id": "moon dust", "percent": 100}], "technique": "direct"},
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
        json={"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "ash%": 0.50, "percent": 100}], "technique": "direct"},
    )
    assert response.status_code == 200
    assert not any("ash%" in w for w in response.json()["warnings"])


def test_api_generate_warns_on_mismatched_ash_pct():
    response = client.post(
        "/recipes/generate",
        json={"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "ash%": 1.50, "percent": 100}], "technique": "direct"},
    )
    assert response.status_code == 200
    assert any("ash%" in w for w in response.json()["warnings"])


def test_api_generate_accepts_poolish_percentage():
    response = client.post(
        "/recipes/generate",
        json={
            "flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 65}, {"pizza_flours_id": WHOLE_WHEAT, "percent": 35}],
            "technique": "poolish",
            "poolish_percentage": 40,
            "hydration_pct": 76,
            "ball_weight_g": 1000,
        },
    )
    assert response.status_code == 200
    assert response.json()["leavening"]["percent_of_flour"] == 40


def test_api_generate_accepts_biga_and_sourdough_percentage():
    biga = client.post(
        "/recipes/generate",
        json={"flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}], "technique": "biga", "biga_percentage": 55},
    )
    assert biga.status_code == 200
    assert biga.json()["leavening"]["percent_of_flour"] == 55

    sourdough = client.post(
        "/recipes/generate",
        json={
            "flours": [{"pizza_flours_id": SOFT_WHEAT_00, "percent": 100}],
            "technique": "sourdough",
            "sourdough_percentage": 25,
        },
    )
    assert sourdough.status_code == 200
    assert sourdough.json()["leavening"]["percent_of_flour"] == 25
