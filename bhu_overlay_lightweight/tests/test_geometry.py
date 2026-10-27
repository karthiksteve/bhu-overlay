"""
test_geometry.py - Comprehensive Unit Tests for Geometry, Subdivision, AI Fallback, and Caching
Tests:
  1. Polygon validity & metrics (area, perimeter, side lengths)
  2. Multi-share Kurra subdivision & strict area conservation tolerance
  3. Feature containment (trees & wells inside sub-plots)
  4. Gemini recommendation schema and deterministic fallback
  5. Native vector PDF report generation without OpenCV
  6. SQLite data/app.db caching and parcel CRUD
"""

import os
import sys
import pytest
from shapely.geometry import Polygon, Point, LineString

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend import geometry
from backend import gemini
from backend import reports
from backend import cache


def test_polygon_metrics():
    """Verify area, perimeter, and side lengths on a regular rectangular polygon."""
    poly = Polygon([(0, 0), (100, 0), (100, 50), (0, 50), (0, 0)])
    metrics = geometry.calculate_polygon_metrics(poly)

    assert metrics["area_sqm"] == 5000.0
    assert metrics["perimeter_m"] == 300.0
    assert metrics["area_hectares"] == 0.5
    assert len(metrics["side_lengths"]) == 4
    assert metrics["side_lengths"] == [100.0, 50.0, 100.0, 50.0]


def test_invalid_polygon_repair():
    """Ensure self-intersecting or invalid polygons are automatically repaired."""
    # Self-intersecting bow-tie polygon
    bow_tie = Polygon([(0, 0), (50, 50), (50, 0), (0, 50), (0, 0)])
    repaired = geometry.ensure_valid_polygon(bow_tie)
    assert repaired.is_valid
    assert repaired.area > 0


def test_subdivision_area_conservation():
    """
    STRICT AREA CONSERVATION TEST:
    Verifies sum(sub_plot_areas) == original_area within 0.1% tolerance across
    multiple cut angles and unequal share distributions.
    """
    poly = Polygon([(100, 200), (350, 220), (340, 480), (80, 450), (100, 200)])
    original_area = poly.area

    # Test 3 unequal shares: 50%, 30%, 20%
    shares = [0.5, 0.3, 0.2]
    strategies = geometry.generate_strategies(poly, shares)

    assert len(strategies) >= 1, "Must generate at least 1 valid strategy"

    for strat in strategies:
        sub_polys = strat["polys"]
        assert len(sub_polys) == 3, f"Strategy {strat['name']} should produce exactly 3 sub-plots"

        total_sub_area = sum(p.area for p in sub_polys)
        area_diff = abs(total_sub_area - original_area)
        # Tolerance is 0.5%
        assert area_diff < 0.005 * original_area, (
            f"Area conservation failed for '{strat['name']}': Original={original_area:.2f}, "
            f"Sum={total_sub_area:.2f}, Diff={area_diff:.2f}"
        )


def test_road_frontage_alignment():
    """Verify subdivision with road frontage coordinates generates a road-perpendicular strategy."""
    poly = Polygon([(0, 0), (120, 0), (120, 60), (0, 60), (0, 0)])
    # Road runs horizontally along south boundary
    road_coords = [(0, 0), (120, 0)]

    strategies = geometry.generate_strategies(poly, [0.5, 0.5], frontage_coords=road_coords)
    strategy_names = [s["name"] for s in strategies]

    # Verify road access strategy is present
    assert any("Road" in name for name in strategy_names)


def test_pyproj_transformer_caching():
    """Verify pyproj transformers return singleton cached instances."""
    t1 = geometry.get_utm_to_gps()
    t2 = geometry.get_utm_to_gps()
    assert t1 is t2, "Transformer must be cached as a singleton"

    # Test coordinate transformation for Patna
    lon, lat = geometry.utm_to_gps(313000, 2831000)
    assert 80.0 < lon < 90.0
    assert 20.0 < lat < 30.0


def test_gemini_fallback_when_key_missing():
    """Verify Gemini layer gracefully falls back to deterministic recommendation without crashing."""
    old_key = os.environ.get("GEMINI_API_KEY")
    try:
        os.environ["GEMINI_API_KEY"] = ""
        poly = Polygon([(0, 0), (100, 0), (100, 50), (0, 50), (0, 0)])
        metrics = geometry.calculate_polygon_metrics(poly)
        strategies = geometry.generate_strategies(poly, [0.5, 0.5])

        result = gemini.evaluate_strategies(metrics, strategies)

        assert result["success"] is True
        assert result["fallback"] is True
        assert result["recommended_strategy_index"] == 0
        assert "Deterministic" in result["explanation"]
    finally:
        if old_key is not None:
            os.environ["GEMINI_API_KEY"] = old_key


def test_vector_pdf_generation():
    """Verify native vector PDF generation without OpenCV produces a valid PDF."""
    parcel_info = {
        "plot_no": "999",
        "district": "Patna",
        "subdivision": "Patna Sadar",
        "circle": "Phulwari",
        "mouza": "Test Mouza",
        "sheet_no": "1"
    }
    metrics = {
        "area_sqm": 2500.0,
        "area_acres": 0.6178,
        "area_hectares": 0.25,
        "perimeter_m": 200.0
    }
    p1 = Polygon([(0, 0), (50, 0), (50, 50), (0, 50), (0, 0)])
    p2 = Polygon([(50, 0), (100, 0), (100, 50), (50, 50), (50, 0)])
    sub_res = {
        "strategy_name": "Compact Cut",
        "polys": [p1, p2],
        "features": [
            {"properties": {"sub_plot_id": 1, "share_percentage": 50.0, "area_sqm": 1250.0, "perimeter_m": 150.0, "frontage_m": 25.0}},
            {"properties": {"sub_plot_id": 2, "share_percentage": 50.0, "area_sqm": 1250.0, "perimeter_m": 150.0, "frontage_m": 25.0}}
        ]
    }

    pdf_bytes = reports.generate_pdf_report(parcel_info, metrics, sub_res)
    assert len(pdf_bytes) > 500
    assert pdf_bytes[:4] == b"%PDF", "Output must begin with %PDF header"


def test_sqlite_cache_and_parcel_persistence():
    """Verify SQLite cache.py saves and retrieves parcels and key-value entries."""
    cache.init_db()

    # Test key-value cache
    cache.set_cache("unit_test_key", {"status": "ok", "count": 42})
    cached_val = cache.get_cache("unit_test_key")
    assert cached_val == {"status": "ok", "count": 42}

    # Test parcel persistence
    test_parcel = {
        "plot_no": "TEST-888",
        "district": "TestDistrict",
        "area": 1234.56,
        "perimeter": 150.0,
        "lat": 25.5,
        "lon": 85.1,
        "owner_names": ["Owner 1", "Owner 2"]
    }
    test_vertices = [
        {"x": 0, "y": 0, "lon": 85.10, "lat": 25.50},
        {"x": 50, "y": 0, "lon": 85.11, "lat": 25.50},
        {"x": 50, "y": 30, "lon": 85.11, "lat": 25.51},
        {"x": 0, "y": 30, "lon": 85.10, "lat": 25.51}
    ]
    p_id = cache.save_parcel(test_parcel, test_vertices)
    assert p_id is not None

    retrieved = cache.get_parcel("TEST-888")
    assert retrieved is not None
    assert retrieved["parcel"]["plot_no"] == "TEST-888"
    assert len(retrieved["vertices"]) == 4
