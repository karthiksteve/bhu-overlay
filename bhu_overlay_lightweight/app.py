"""
app.py - Bhu-Overlay Flask Server & Routing Gateway
Lightweight, modular entry point connecting frontend requests to backend modules:
  - backend/bhunaksha.py  (Government GIS API client & proxy)
  - backend/gis.py        (ArcGIS vector querying & spatial layers)
  - backend/geometry.py   (Deterministic Shapely calculations & subdivision)
  - backend/gemini.py     (AI recommendation & legal evaluation layer)
  - backend/reports.py    (Native vector PDF report generator)
  - backend/cache.py      (SQLite data/app.db & memory caching)
"""

import os
import sys
import json
from shapely.geometry import Polygon, Point, LineString
import shapely.wkt
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# Ensure backend directory is in Python path
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend import bhunaksha
from backend import gis
from backend import geometry
from backend import gemini
from backend import reports
from backend import cache

# Initialize SQLite database schema
cache.init_db()

# Initialize session cookies if available
bhunaksha.init_session()

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)


# ---------------------------------------------------------------------------
# Frontend Static File Serving
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve main frontend application."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve frontend CSS, JS, and assets."""
    if os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------------------------------------------------------------------------
# BhuNaksha Administrative & Bounding Box Endpoints
# ---------------------------------------------------------------------------

@app.route("/proxy/Levels/ListsAfterLevel", methods=["POST"])
def proxy_lists_after_level():
    """Cascading dropdown data (District -> Subdiv -> Circle -> Mouza -> Sheet)."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    state = data.get("state", bhunaksha.STATE_CONFIG["code"])
    level = data.get("level", "0")
    codes = data.get("codes", "") or data.get("parent_code", "")
    result = bhunaksha.get_lists_after_level(state, level, codes)
    return jsonify(result)


@app.route("/proxy/MapInfo/getVVVVExtentGeoref", methods=["POST"])
def proxy_extent():
    """Fetch sheet bounding box in GPS (4326) or UTM (0)."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    state = data.get("state", bhunaksha.STATE_CONFIG["code"])
    gis_levels = data.get("gisLevels") or data.get("gis_levels") or data.get("layers", "")
    srs = data.get("srs", "4326")
    result = bhunaksha.get_vvvv_extent(state, gis_levels, srs)
    return jsonify(result)


@app.route("/proxy/MapInfo/getPlotAtXY", methods=["POST"])
def proxy_plot_at_xy():
    """Lookup plot number from local UTM coordinates."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    state = data.get("state", bhunaksha.STATE_CONFIG["code"])
    giscode = data.get("giscode", "")
    x = data.get("x", 0)
    y = data.get("y", 0)
    result = bhunaksha.get_plot_at_xy(state, giscode, x, y)
    return jsonify(result)


@app.route("/proxy/MapInfo/getPlotAtGPS", methods=["POST"])
def proxy_plot_at_gps():
    """Lookup plot number from map click GPS coordinate."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    state = data.get("state", bhunaksha.STATE_CONFIG["code"])
    giscode = data.get("giscode", "")
    levels = data.get("levels", "")
    lat = data.get("lat")
    lon = data.get("lon")
    result = bhunaksha.get_plot_at_gps(state, giscode, levels, lat, lon)
    return jsonify(result)


@app.route("/proxy/MapInfo/getPointsfromPNIU", methods=["POST"])
def proxy_pniu():
    """Lookup parcel by 14-digit PNIU code."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    state = data.get("state", bhunaksha.STATE_CONFIG["code"])
    pniu = data.get("pniu", "")
    gis_code = data.get("gisCode") or data.get("giscode", "")
    result = bhunaksha.get_plot_from_pniu(state, pniu, gis_code)
    return jsonify(result)


@app.route("/proxy/MapInfo/getPlotDetailsAndInspection", methods=["POST"])
def proxy_plot_details():
    """Fetch parcel geometry, vertices, boundary measurements, and ownership."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    state = data.get("state", bhunaksha.STATE_CONFIG["code"])
    giscode = data.get("giscode", "")
    plot_no = data.get("plot_no", "")
    levels = data.get("levels", "")
    result = bhunaksha.get_plot_details(state, giscode, plot_no, levels)
    return jsonify(result)


@app.route("/proxy/WMS", methods=["GET"])
def proxy_wms():
    """Proxy cadastral WMS map tiles with in-memory and disk caching."""
    tile_bytes, status = bhunaksha.proxy_wms_tile(request.args.to_dict())
    resp = Response(tile_bytes, status=status, content_type="image/png")
    resp.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=3600"
    return resp


# ---------------------------------------------------------------------------
# Land Subdivision & AI Recommendation Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/parcel/<plot_no>/subdivide", methods=["POST"])
def subdivide_parcel(plot_no):
    """
    Generate multiple deterministic subdivision strategies,
    consult Gemini for recommendation, and return GeoJSON FeatureCollection.
    """
    data = request.get_json(silent=True) or {}
    shares_raw = data.get("shares")
    if not shares_raw or not isinstance(shares_raw, list):
        return jsonify({"error": "Missing or invalid 'shares' list"}), 400

    shares = []
    for s in shares_raw:
        if isinstance(s, dict):
            val = s.get("fraction") or s.get("percentage") or s.get("share") or s.get("ratio") or 0.0
            if val <= 1.0 and any(isinstance(x, dict) and (x.get("fraction") or 0) <= 1.0 for x in shares_raw):
                val = val * 100.0
            shares.append(float(val))
        else:
            shares.append(float(s))

    trees_and_wells = data.get("features", [])
    user_preferences = data.get("user_preferences", "")
    parcel_id = request.args.get("parcel_id")
    if str(parcel_id).strip().lower() in ("", "none", "null", "undefined"):
        parcel_id = None

    parcel_data = cache.get_parcel(plot_no, parcel_id=parcel_id)
    if not parcel_data or not parcel_data.get("vertices"):
        if data.get("vertices"):
            parcel_data = {"vertices": data["vertices"]}
        elif data.get("parcel_info") and data["parcel_info"].get("vertices"):
            parcel_data = {"vertices": data["parcel_info"]["vertices"]}
        else:
            giscode = data.get("giscode") or (data.get("parcel_info") or {}).get("giscode", "")
            fetched = bhunaksha.get_plot_details(bhunaksha.STATE_CONFIG["code"], giscode, plot_no)
            if isinstance(fetched, dict) and fetched.get("success") and fetched.get("vertices"):
                parcel_data = fetched
            else:
                return jsonify({"error": f"Parcel {plot_no} not found or missing geometric data"}), 404

    vertices = parcel_data["vertices"]
    poly_coords = [(v["x"], v["y"]) for v in vertices]
    if poly_coords[0] != poly_coords[-1]:
        poly_coords.append(poly_coords[0])

    poly = Polygon(poly_coords)
    poly = geometry.ensure_valid_polygon(poly)

    # Convert coordinates for GIS checks
    gps_coords = [(v["lon"], v["lat"]) for v in vertices]
    if gps_coords[0] != gps_coords[-1]:
        gps_coords.append(gps_coords[0])
    poly_gps = Polygon(gps_coords)
    poly_gps = geometry.ensure_valid_polygon(poly_gps)

    # Query nearby roads and rivers
    roads, rivers = gis.get_nearby_vector_features(poly_gps)
    frontage_utm = None
    best_road = roads[0] if roads else None
    if best_road:
        frontage_utm = [geometry.gps_to_utm(pt[0], pt[1]) for pt in best_road["geometry"].coords]

    river_utm = None
    best_river = rivers[0] if rivers else None
    if best_river:
        river_utm = [geometry.gps_to_utm(pt[0], pt[1]) for pt in best_river["geometry"].coords]

    # Generate deterministic strategies
    strategies = geometry.generate_strategies(poly, shares, frontage_utm, river_utm)
    if not strategies:
        return jsonify({"error": "Failed to generate any valid division strategies"}), 500

    # Calculate metrics for each sub-plot
    for strat in strategies:
        strat_stats = []
        for sp in strat["polys"]:
            f_len = 0
            if frontage_utm:
                fl_line = LineString(frontage_utm)
                f_len = sp.buffer(5.0).intersection(fl_line).length

            r_len = 0
            if river_utm:
                rl_line = LineString(river_utm)
                r_len = sp.buffer(5.0).intersection(rl_line).length

            c_feats = 0
            sp_gps = Polygon([geometry.utm_to_gps(x, y) for x, y in sp.exterior.coords])
            for feat in trees_and_wells:
                pt_gps = Point(feat["x"], feat["y"])
                if sp_gps.contains(pt_gps) or sp_gps.distance(pt_gps) < 1e-5:
                    c_feats += 1

            strat_stats.append({"frontage_m": f_len, "river_frontage_m": r_len, "features": c_feats})
        strat["sub_plot_stats"] = strat_stats

    # Consult Gemini AI if enabled, otherwise use deterministic fallback
    use_ai = data.get("use_ai", True)
    parcel_metrics = geometry.calculate_polygon_metrics(poly)

    if use_ai:
        ai_res = gemini.evaluate_strategies(parcel_metrics, strategies, best_road, best_river, user_preferences)
    else:
        ai_res = {
            "recommended_strategy_index": 0,
            "explanation": f"Deterministic geometric partition calculated without AI ({strategies[0]['name']}).",
            "warnings": [],
            "fallback": True
        }

    rec_idx = ai_res.get("recommended_strategy_index", 0)
    best_strat = strategies[rec_idx]

    # Build GeoJSON FeatureCollection
    features = []
    for i, sp in enumerate(best_strat["polys"]):
        sub_gps = [geometry.utm_to_gps(x, y) for x, y in sp.exterior.coords]
        sp_gps_poly = Polygon(sub_gps)

        # Identify contained user-drawn features
        contained = []
        for feat in trees_and_wells:
            pt = Point(feat["x"], feat["y"])
            if sp_gps_poly.contains(pt) or sp_gps_poly.distance(pt) < 1e-5:
                contained.append(feat)

        f_len = 0
        if frontage_utm:
            f_len = sp.buffer(5.0).intersection(LineString(frontage_utm)).length

        features.append({
            "type": "Feature",
            "properties": {
                "sub_plot_id": i + 1,
                "share_percentage": shares[i],
                "area_sqm": round(sp.area, 2),
                "perimeter_m": round(sp.length, 2),
                "frontage_m": round(f_len, 2),
                "contained_features": contained
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [sub_gps]
            }
        })

    frontage_gps = [geometry.utm_to_gps(x, y) for x, y in frontage_utm] if frontage_utm else []

    return jsonify({
        "type": "FeatureCollection",
        "features": features,
        "strategy_name": best_strat["name"],
        "recommended_strategy_index": rec_idx,
        "llm_explanation": ai_res.get("explanation", ""),
        "llm_warnings": ai_res.get("warnings", []),
        "llm_failed": ai_res.get("fallback", False),
        "frontage_coords": frontage_gps
    })


# ---------------------------------------------------------------------------
# Report Generation & Data Export Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/parcel/<plot_no>/generate_report", methods=["POST"])
def generate_report(plot_no):
    """Generate official PDF Kurra Land Division or LPM Report."""
    data = request.get_json(silent=True) or {}
    parcel_id = request.args.get("parcel_id")

    parcel_data = cache.get_parcel(plot_no, parcel_id=parcel_id)
    if not parcel_data or not parcel_data.get("vertices"):
        return jsonify({"error": "Parcel not found"}), 404

    vertices = parcel_data["vertices"]
    poly_coords = [(v["x"], v["y"]) for v in vertices]
    poly = Polygon(poly_coords)
    poly = geometry.ensure_valid_polygon(poly)
    metrics = geometry.calculate_polygon_metrics(poly)

    sub_result = None
    ai_evaluation = None
    p_info = data.get("parcel_info") or {}

    # Case 1: Frontend sent explicit subdivision results (from interactive UI session)
    if data.get("subdivisions") and len(data["subdivisions"]) > 1:
        sub_features = data["subdivisions"]
        sub_polys = []
        for f in sub_features:
            c = f.get("geometry", {}).get("coordinates", [])
            if c and len(c) > 0:
                sub_polys.append(Polygon(c[0]))

        frontage_coords = data.get("frontage") or []
        strat_name = p_info.get("strategy_name") or data.get("strategy_name") or "Kurra Division"
        sub_result = {
            "strategy_name": strat_name,
            "polys": sub_polys,
            "features": sub_features,
            "frontage_coords": frontage_coords if len(frontage_coords) >= 2 else None
        }
        explanation = (
            p_info.get("llm_explanation") or
            data.get("llm_explanation") or
            data.get("dispute_notes") or
            "Subdivision calculated in compliance with Rule 109 of the Revenue Code."
        )
        ai_evaluation = {"explanation": explanation}

    # Case 2: Programmatic subdivision request with shares
    elif data.get("shares"):
        shares_raw = data.get("shares")
        shares = []
        for s in shares_raw:
            if isinstance(s, dict):
                val = s.get("fraction") or s.get("percentage") or s.get("share") or s.get("ratio") or 0.0
                if val <= 1.0 and any(isinstance(x, dict) and (x.get("fraction") or 0) <= 1.0 for x in shares_raw):
                    val = val * 100.0
                shares.append(float(val))
            else:
                shares.append(float(s))

        strategies = geometry.generate_strategies(poly, shares)
        best_strat = strategies[0] if strategies else None
        if best_strat:
            sub_features = []
            for i, sp in enumerate(best_strat["polys"]):
                sub_features.append({
                    "properties": {
                        "sub_plot_id": i + 1,
                        "share_percentage": shares[i] if i < len(shares) else 0,
                        "area_sqm": round(sp.area, 2),
                        "perimeter_m": round(sp.length, 2),
                        "frontage_m": 0.0
                    }
                })
            sub_result = {
                "strategy_name": best_strat["name"],
                "polys": best_strat["polys"],
                "features": sub_features,
                "frontage_coords": None
            }
        ai_evaluation = {
            "explanation": data.get("dispute_notes") or "Subdivision calculated in compliance with Rule 109 of the Revenue Code."
        }

    # Case 3: Intact single-parcel LPM report
    else:
        sub_result = None
        ai_evaluation = None

    pdf_bytes = reports.generate_pdf_report(
        parcel_data["parcel"],
        metrics,
        sub_result,
        ai_evaluation,
        parcel_poly=poly
    )

    # Save report reference in DB & disk
    os.makedirs("static/reports", exist_ok=True)
    filename = f"Kurra_Report_{plot_no}.pdf" if sub_result else f"LPM_Report_{plot_no}.pdf"
    rel_url = f"/static/reports/{filename}"
    disk_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "reports", filename)
    with open(disk_path, "wb") as f:
        f.write(pdf_bytes)

    if parcel_data["parcel"].get("id"):
        cache.save_report(parcel_data["parcel"]["id"], rel_url, filename)

    return Response(pdf_bytes, mimetype="application/pdf", headers={
        "Content-Disposition": f"attachment; filename={filename}"
    })


# ---------------------------------------------------------------------------
# Batch Sheet Vector Scraper & Export Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/sheet/scrape_batch", methods=["POST"])
def scrape_sheet_batch():
    """Auto-discovers and caches parcel geometries across a cadastral sheet using a batch grid."""
    data = request.get_json(silent=True) or {}
    state = str(data.get("state") or bhunaksha.STATE_CONFIG["code"])
    giscode = str(data.get("giscode") or "")
    levels = str(data.get("levels") or "")
    batch_index = int(data.get("batch_index", 0))
    batch_size = max(1, int(data.get("batch_size", 65)))
    grid_step = max(15.0, float(data.get("grid_step", 35.0)))

    extent = bhunaksha.get_vvvv_extent(state, levels, srs="4326")
    if not extent or "xmin" not in extent or (extent.get("xmin") == 0 and extent.get("ymin") == 0):
        extent = bhunaksha.get_vvvv_extent(state, levels, srs="0")

    # Derive bounding box in UTM meters
    if extent and "xmin" in extent and not (extent.get("xmin") == 0 and extent.get("ymin") == 0):
        xmin, ymin = extent["xmin"], extent["ymin"]
        xmax, ymax = extent["xmax"], extent["ymax"]
        if xmax <= 180:
            min_x, min_y = geometry.gps_to_utm(xmin, ymin)
            max_x, max_y = geometry.gps_to_utm(xmax, ymax)
        else:
            min_x, min_y = xmin, ymin
            max_x, max_y = xmax, ymax
    else:
        min_x, min_y = 251000.0, 2779000.0
        max_x, max_y = 253000.0, 2781000.0

    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y

    # Build regular sampling grid
    grid_pts = []
    curr_x = min_x + grid_step / 2.0
    while curr_x < max_x:
        curr_y = min_y + grid_step / 2.0
        while curr_y < max_y:
            grid_pts.append((round(curr_x, 1), round(curr_y, 1)))
            curr_y += grid_step
        curr_x += grid_step

    total_pts = len(grid_pts)
    start_idx = batch_index * batch_size
    end_idx = min(start_idx + batch_size, total_pts)
    curr_batch = grid_pts[start_idx:end_idx] if start_idx < total_pts else []
    is_done = end_idx >= total_pts

    # Load known parcel polygons from SQLite cache to skip redundant lookups
    conn = cache.get_db()
    known_polys = []
    saved_plot_nos = set()
    try:
        rows = conn.execute("SELECT id, plot_no, geometry_wkt FROM parcels WHERE geometry_wkt IS NOT NULL").fetchall()
        for r in rows:
            saved_plot_nos.add(str(r["plot_no"]))
            try:
                known_polys.append(shapely.wkt.loads(r["geometry_wkt"]))
            except Exception:
                pass
    finally:
        conn.close()

    new_plots_found = []
    for px, py in curr_batch:
        glon, glat = geometry.utm_to_gps(px, py)
        pt_gps = Point(glon, glat)

        inside_known = any(poly.contains(pt_gps) or poly.distance(pt_gps) < 1e-5 for poly in known_polys)
        if inside_known:
            continue

        res = bhunaksha.get_plot_at_xy(state, giscode, px, py)
        p_num = str(res.get("plot_no") or res.get("kide") or res.get("plotno") or "").strip()
        if p_num and p_num != "0" and p_num not in saved_plot_nos and p_num not in new_plots_found:
            new_plots_found.append(p_num)
            saved_plot_nos.add(p_num)
            p_detail = bhunaksha.get_plot_details(state, giscode, p_num, levels)
            if isinstance(p_detail, dict) and p_detail.get("success") and p_detail.get("vertices"):
                coords = [(v["lon"], v["lat"]) for v in p_detail["vertices"]]
                if len(coords) >= 3:
                    known_polys.append(Polygon(coords))

    return jsonify({
        "success": True,
        "batch_index": batch_index,
        "scanned_points_in_batch": len(curr_batch),
        "total_points": total_pts,
        "new_plots_found": new_plots_found,
        "total_plots_saved": len(saved_plot_nos),
        "is_done": is_done
    })


@app.route("/api/sheet/export_geojson", methods=["GET"])
def export_sheet_geojson():
    """Export all discovered parcels in the current sheet as a unified GeoJSON FeatureCollection."""
    state = request.args.get("state", bhunaksha.STATE_CONFIG["code"])
    levels = request.args.get("levels", "")
    levels_parts = [p.strip() for p in levels.split(",") if p.strip()]

    conn = cache.get_db()
    try:
        if len(levels_parts) >= 7 and levels_parts[6]:
            sheet_no = levels_parts[6]
            mouza = levels_parts[3] if len(levels_parts) > 3 else ""
            rows = conn.execute(
                "SELECT * FROM parcels WHERE (sheet_no = ? OR sheet_no = '') AND (mouza = ? OR mouza = '')",
                (sheet_no, mouza)
            ).fetchall()
            if not rows:
                rows = conn.execute("SELECT * FROM parcels").fetchall()
        else:
            rows = conn.execute("SELECT * FROM parcels").fetchall()

        features = []
        for r in rows:
            p_dict = dict(r)
            p_id = p_dict["id"]
            v_rows = conn.execute(
                "SELECT lon, lat FROM parcel_vertices WHERE parcel_id = ? ORDER BY sequence_order ASC",
                (p_id,)
            ).fetchall()
            if len(v_rows) >= 3:
                coords = [[v["lon"], v["lat"]] for v in v_rows]
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                features.append({
                    "type": "Feature",
                    "properties": {
                        "plot_no": p_dict["plot_no"],
                        "khata_no": p_dict.get("khata_no", ""),
                        "pniu": p_dict.get("pniu", ""),
                        "area_sqm": p_dict.get("area", 0.0),
                        "perimeter_m": p_dict.get("perimeter", 0.0),
                        "district": p_dict.get("district", ""),
                        "circle": p_dict.get("circle", ""),
                        "mouza": p_dict.get("mouza", ""),
                        "sheet_no": p_dict.get("sheet_no", "")
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                })

        geojson = {
            "type": "FeatureCollection",
            "total_parcels": len(features),
            "features": features
        }
        fname = f"Sheet_{levels_parts[6] if len(levels_parts) >= 7 else 'Vectors'}.geojson"
        return Response(json.dumps(geojson, indent=2), mimetype="application/json", headers={
            "Content-Disposition": f"attachment; filename={fname}"
        })
    finally:
        conn.close()


@app.route("/proxy/Export/GeoJSON/<plot_no>", methods=["GET"])
def export_geojson(plot_no):
    """Export parcel boundary geometry as GeoJSON."""
    parcel_id = request.args.get("parcel_id")
    parcel_data = cache.get_parcel(plot_no, parcel_id=parcel_id)
    if not parcel_data or not parcel_data.get("vertices"):
        return jsonify({"error": "Parcel not found"}), 404

    coords = [[v["lon"], v["lat"]] for v in parcel_data["vertices"]]
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": parcel_data["parcel"],
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords]
            }
        }]
    }
    return Response(json.dumps(geojson, indent=2), mimetype="application/json", headers={
        "Content-Disposition": f"attachment; filename=Plot_{plot_no}.geojson"
    })


@app.route("/proxy/Export/CSV/<plot_no>", methods=["GET"])
def export_csv(plot_no):
    """Export parcel boundary vertices and side measurements as CSV."""
    parcel_id = request.args.get("parcel_id")
    parcel_data = cache.get_parcel(plot_no, parcel_id=parcel_id)
    if not parcel_data or not parcel_data.get("vertices"):
        return jsonify({"error": "Parcel not found"}), 404

    lines = ["vertex_order,utm_x,utm_y,gps_lon,gps_lat,side_length_meters"]
    vertices = parcel_data["vertices"]
    segments = parcel_data.get("segments", [])

    for i, v in enumerate(vertices):
        seg_len = segments[i]["length_meters"] if i < len(segments) else 0.0
        lines.append(f"{v['sequence_order']},{v['x']},{v['y']},{v['lon']},{v['lat']},{seg_len}")

    csv_data = "\n".join(lines)
    return Response(csv_data, mimetype="text/csv", headers={
        "Content-Disposition": f"attachment; filename=Plot_{plot_no}_Coordinates.csv"
    })


# ---------------------------------------------------------------------------
# Server Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting Bhu-Overlay API Server on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
