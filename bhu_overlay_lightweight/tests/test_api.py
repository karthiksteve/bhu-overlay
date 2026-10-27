"""
test_api.py - Integration and Route Verification Tests for Flask Gateway
Tests all primary API endpoints used by the frontend.
"""

import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    with app.app.test_client() as client:
        yield client


def test_home_page_serves_frontend(client):
    """GET / serves frontend index.html."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Bhu-Overlay" in resp.data or b"Cadastral" in resp.data


def test_proxy_dropdowns(client):
    """POST /proxy/Levels/ListsAfterLevel returns administrative divisions."""
    resp = client.post("/proxy/Levels/ListsAfterLevel", json={"state": "10", "level": "0", "codes": ""})
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_proxy_extent_cached(client):
    """POST /proxy/MapInfo/getVVVVExtentGeoref returns sheet extent."""
    resp = client.post("/proxy/MapInfo/getVVVVExtentGeoref", json={
        "state": "10",
        "gisLevels": "38,01,02,0118,CS,06,02,",
        "srs": "4326"
    })
    assert resp.status_code == 200
    ext = resp.get_json()
    assert "xmin" in ext and "ymin" in ext


def test_plot_details_and_inspection(client):
    """POST /proxy/MapInfo/getPlotDetailsAndInspection fetches parcel 1623 from cache."""
    resp = client.post("/proxy/MapInfo/getPlotDetailsAndInspection", json={
        "state": "10",
        "plot_no": "1623",
        "giscode": "CS0701010050215/10600"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["parcel"]["plot_no"] == "1623"
    assert len(data["vertices"]) > 0


def test_subdivide_endpoint(client):
    """POST /api/parcel/1623/subdivide produces sub-plot FeatureCollection."""
    resp = client.post("/api/parcel/1623/subdivide", json={
        "shares": [50.0, 50.0],
        "use_ai": False
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 2
    # Verify area conservation on returned GeoJSON
    sub_areas = [f["properties"]["area_sqm"] for f in data["features"]]
    total_sub_area = sum(sub_areas)
    assert abs(total_sub_area - 8624.53) < 20.0  # < 0.25% variance


def test_generate_pdf_report_endpoint(client):
    """POST /api/parcel/1623/generate_report generates valid %PDF document."""
    resp = client.post("/api/parcel/1623/generate_report", json={
        "shares": [50.0, 50.0],
        "dispute_notes": "Court partition case test"
    })
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_export_geojson_endpoint(client):
    """GET /proxy/Export/GeoJSON/1623 returns downloadable GeoJSON."""
    resp = client.get("/proxy/Export/GeoJSON/1623")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "application/json"
    data = resp.get_json()
    assert data["type"] == "FeatureCollection"
    assert data["features"][0]["geometry"]["type"] == "Polygon"


def test_export_csv_endpoint(client):
    """GET /proxy/Export/CSV/1623 returns vertex coordinate CSV."""
    resp = client.get("/proxy/Export/CSV/1623")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("Content-Type", "")
    lines = resp.data.decode("utf-8").strip().split("\n")
    assert len(lines) > 5
    assert "vertex_order,utm_x,utm_y,gps_lon,gps_lat" in lines[0]


def test_generate_lpm_report_intact_parcel(client):
    """POST /api/parcel/1623/generate_report without shares generates official intact LPM report."""
    resp = client.post("/api/parcel/1623/generate_report", json={})
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert "LPM_Report_1623.pdf" in resp.headers.get("Content-Disposition", "")


def test_generate_kurra_report_with_explicit_subdivisions(client):
    """POST /api/parcel/1623/generate_report with UI subdivisions generates exact Kurra report."""
    subdivide_resp = client.post("/api/parcel/1623/subdivide", json={"shares": [60.0, 40.0], "use_ai": False})
    sub_data = subdivide_resp.get_json()

    report_payload = {
        "subdivisions": sub_data["features"],
        "strategy_name": sub_data.get("strategy_name", "Test Strategy"),
        "parcel_info": {
            "plot_no": "1623",
            "strategy_name": sub_data.get("strategy_name", "Test Strategy"),
            "llm_explanation": "Approved under Rule 109."
        }
    }
    resp = client.post("/api/parcel/1623/generate_report", json=report_payload)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert "Kurra_Report_1623.pdf" in resp.headers.get("Content-Disposition", "")


def test_scrape_sheet_batch_endpoint(client):
    """POST /api/sheet/scrape_batch processes grid batch and returns batch status."""
    resp = client.post("/api/sheet/scrape_batch", json={
        "state": "10",
        "giscode": "CS38010201181630602",
        "levels": "38,01,02,0118,CS,06,02,",
        "batch_index": 0,
        "batch_size": 20,
        "grid_step": 50.0
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["batch_index"] == 0
    assert "total_points" in data
    assert "total_plots_saved" in data
    assert isinstance(data["new_plots_found"], list)


def test_export_sheet_geojson_endpoint(client):
    """GET /api/sheet/export_geojson returns unified GeoJSON FeatureCollection."""
    resp = client.get("/api/sheet/export_geojson?state=10&levels=38,01,02,0118,CS,06,02,")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "application/json"
    data = resp.get_json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert data["total_parcels"] > 0

