"""
bhunaksha.py - Government Cadastral BhuNaksha GIS Client & Proxy
Handles session management, rate limiting, cascading administrative dropdowns,
parcel geometry fetching, coordinate conversions, and WMS tile caching.
"""

import os
import sys
import time
import math
import json
import hashlib
import requests
import urllib3
from shapely.geometry import Polygon, Point
import shapely.wkt

from . import cache
from . import geometry

# State configuration (Centralized & configurable for future expansion e.g. Tamil Nadu)
STATE_CONFIG = {
    "code": os.environ.get("STATE_CODE", "10"),
    "name": os.environ.get("STATE_NAME", "Bihar"),
    "bhunaksha_url": os.environ.get("BHUNAKSHA_URL", "https://bhunaksha.bihar.gov.in"),
    "gis_url": os.environ.get("GIS_URL", "https://gisserver.bihar.gov.in/arcgis/rest/services")
}

VERIFY_SSL = os.environ.get("VERIFY_SSL", "0").lower() in ("1", "true", "yes")
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "session_cookies.json")
WMS_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "wms_cache")
os.makedirs(WMS_CACHE_DIR, exist_ok=True)

# Shared HTTP session
session = requests.Session()
session.verify = VERIFY_SSL

# Resilience & Rate limiting state
_LAST_REQUEST_TIME = 0.0
_MIN_REQUEST_INTERVAL = 0.15  # 150 ms between requests to respect server
_SERVER_OFFLINE_UNTIL = 0.0
_COOLDOWN_SECONDS = 30.0
_TILE_MEMORY_CACHE = {}


def _rate_limit():
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_TIME = time.time()


def mark_offline():
    global _SERVER_OFFLINE_UNTIL
    _SERVER_OFFLINE_UNTIL = time.time() + _COOLDOWN_SECONDS


def is_offline():
    return time.time() < _SERVER_OFFLINE_UNTIL


def save_cookies():
    try:
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(requests.utils.dict_from_cookiejar(session.cookies), f)
    except Exception:
        pass


def load_cookies():
    try:
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
                session.cookies.update(requests.utils.cookiejar_from_dict(cookies))
                return True
    except Exception:
        pass
    return False


def init_session(force=False):
    """Initialize or reuse session cookies with BhuNaksha."""
    if is_offline():
        return False

    if not force and load_cookies():
        return True

    try:
        base_url = STATE_CONFIG["bhunaksha_url"]
        st = STATE_CONFIG["code"]
        session.get(f"{base_url}/{st}/index.jsp", timeout=6)
        session.post(f"{base_url}/{st}/indexmain.jsp", data={"state": st}, timeout=6)
        save_cookies()
        return True
    except Exception as e:
        mark_offline()
        return False


def safe_post(url, data=None, headers=None, timeout=8):
    """Perform rate-limited POST with error boundary."""
    if is_offline():
        return None

    _rate_limit()
    try:
        r = session.post(url, data=data, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r
        if r.status_code in (500, 502, 503, 504):
            mark_offline()
    except Exception:
        mark_offline()
    return None


def get_lists_after_level(state, level, codes):
    """
    Fetch cascading administrative dropdown items.
    Checks SQLite / Memory cache first.
    """
    state = str(state or STATE_CONFIG["code"])
    level = str(level or "0")
    codes = str(codes or "")

    cache_key = f"dropdown_{state}_{level}_{codes}"
    cached = cache.get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{STATE_CONFIG['bhunaksha_url']}/rest/Levels/ListsAfterLevel"
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = safe_post(url, data={"state": state, "level": level, "codes": codes}, headers=headers)
    if r and r.status_code == 200:
        try:
            data = r.json()
            cache.set_cache(cache_key, data)
            return data
        except Exception:
            pass
    return []


def get_vvvv_extent(state, gis_levels, srs="4326"):
    """
    Fetch bounding box extent for village sheet (GPS EPSG:4326 or UTM 0).
    """
    state = str(state or STATE_CONFIG["code"])
    gis_levels = str(gis_levels or "")
    srs = str(srs or "4326")

    cache_key = f"extent_{state}_{gis_levels}_{srs}"
    cached = cache.get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{STATE_CONFIG['bhunaksha_url']}/rest/MapInfo/getVVVVExtentGeoref"
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = safe_post(url, data={"state": state, "gisLevels": gis_levels, "srs": srs}, headers=headers)
    if r and r.status_code == 200:
        try:
            data = r.json()
            cache.set_cache(cache_key, data)
            return data
        except Exception:
            pass
    return {"error": "Extent not available"}


def get_plot_at_xy(state, giscode, x, y):
    """Look up plot number by local UTM coordinates."""
    state = str(state or STATE_CONFIG["code"])
    cache_key = f"plot_at_xy_{state}_{giscode}_{round(float(x), 2)}_{round(float(y), 2)}"
    cached = cache.get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{STATE_CONFIG['bhunaksha_url']}/rest/MapInfo/getPlotAtXY"
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = safe_post(url, data={"state": state, "giscode": giscode, "x": x, "y": y}, headers=headers)
    if r and r.status_code == 200:
        try:
            data = r.json()
            cache.set_cache(cache_key, data)
            return data
        except Exception:
            pass
    return {"plot_no": ""}


def get_plot_at_gps(state, giscode, levels, lat, lon):
    """
    Reverse geocodes a map click from GPS (lon, lat) to a plot number.
    1. Checks if point falls inside any cached parcel in data/app.db.
    2. Otherwise transforms GPS to UTM and queries BhuNaksha.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        return {"error": "Invalid coordinates"}, 400

    # 1. Search cached parcels in SQLite
    conn = cache.get_db()
    try:
        rows = conn.execute("SELECT id, plot_no, geometry_wkt FROM parcels WHERE geometry_wkt IS NOT NULL").fetchall()
        pt = Point(lon, lat)
        for r in rows:
            try:
                poly = shapely.wkt.loads(r["geometry_wkt"])
                # Check point in polygon in GPS coordinates
                if poly.contains(pt) or poly.distance(pt) < 1e-5:
                    return {"kide": str(r["plot_no"]), "cached": True}
            except Exception:
                continue
    finally:
        conn.close()

    # 2. Transform GPS to UTM
    try:
        utm_x, utm_y = geometry.gps_to_utm(lon, lat)
        res = get_plot_at_xy(state, giscode, utm_x, utm_y)
        return res
    except Exception as e:
        return {"error": f"Plot lookup failed: {e}"}, 500


def get_plot_from_pniu(state, pniu, gis_code):
    """Search plot details from 14-digit PNIU code."""
    state = str(state or STATE_CONFIG["code"])
    cache_key = f"pniu_{state}_{gis_code}_{pniu}"
    cached = cache.get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{STATE_CONFIG['bhunaksha_url']}/rest/MapInfo/getPointsfromPNIU"
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = safe_post(url, data={"state": state, "pniu": pniu, "gisCode": gis_code}, headers=headers)
    if r and r.status_code == 200:
        try:
            data = r.json()
            cache.set_cache(cache_key, data)
            return data
        except Exception:
            pass
    return {"error": "PNIU plot not found"}


def get_plot_details(state, giscode, plot_no, levels=""):
    """
    Retrieve full parcel geometry, ownership, and boundary measurements.
    Returns from data/app.db if cached; otherwise fetches from government REST API.
    """
    state = str(state or STATE_CONFIG["code"])
    plot_no = str(plot_no)

    # 1. Check local SQLite cache first
    cached_data = cache.get_parcel(plot_no)
    if cached_data and cached_data.get("parcel") and cached_data.get("vertices"):
        p = cached_data["parcel"]
        v_list = cached_data["vertices"]
        s_list = cached_data["segments"]

        # Parse polygon from vertices to ensure geometry fields
        poly_coords = [(v["lon"], v["lat"]) for v in v_list]
        return {
            "success": True,
            "cached": True,
            "parcel": {
                "id": p["id"],
                "plot_no": p["plot_no"],
                "plot_id": p.get("plot_id", ""),
                "khata_no": p.get("khata_no", ""),
                "pniu": p.get("pniu", ""),
                "area": p["area"],
                "area_acres": round(p["area"] * 0.000247105, 4) if p.get("area") else 0.0,
                "perimeter": p["perimeter"],
                "lat": p["lat"],
                "lon": p["lon"],
                "district": p["district"],
                "subdivision": p["subdivision"],
                "circle": p["circle"],
                "mouza": p["mouza"],
                "sheet_no": p["sheet_no"],
                "owner_names": p.get("owner_names", [])
            },
            "vertices": [{
                "id": v.get("id"),
                "x": v["x"],
                "y": v["y"],
                "lon": v["lon"],
                "lat": v["lat"],
                "sequence": v["sequence_order"]
            } for v in v_list],
            "segments": [{
                "start_vertex": s["start_vertex_index"],
                "end_vertex": s["end_vertex_index"],
                "length_meters": s["length_meters"],
                "bearing": s.get("bearing", 0.0)
            } for s in s_list],
            "report": cached_data.get("report")
        }

    # 2. If not cached, query BhuNaksha /rest/MapInfo/getPlotGeom
    url = f"{STATE_CONFIG['bhunaksha_url']}/rest/MapInfo/getPlotGeom"
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    r = safe_post(url, data={"state": state, "giscode": giscode, "plotno": plot_no}, headers=headers)

    if not r or r.status_code != 200:
        return {"success": False, "error": f"Plot {plot_no} not found or server offline"}, 404

    try:
        geom_json = r.json()
        wkt_str = geom_json.get("wkt") or geom_json.get("geom")
        if not wkt_str:
            return {"success": False, "error": "Parcel geometry missing from response"}, 400

        poly_utm = shapely.wkt.loads(wkt_str)
        if not poly_utm.is_valid:
            poly_utm = poly_utm.buffer(0)

        # Compute vertices in UTM and GPS
        coords_utm = list(poly_utm.exterior.coords)
        vertices = []
        gps_coords = []
        for idx, (ux, uy) in enumerate(coords_utm[:-1]):
            glon, glat = geometry.utm_to_gps(ux, uy)
            vertices.append({"x": ux, "y": uy, "lon": glon, "lat": glat, "sequence_order": idx})
            gps_coords.append((glon, glat))

        poly_gps = Polygon(gps_coords)
        metrics = geometry.calculate_polygon_metrics(poly_utm)

        # Parse segments
        segments = []
        for i in range(len(vertices)):
            v1 = vertices[i]
            v2 = vertices[(i + 1) % len(vertices)]
            length = math.hypot(v2["x"] - v1["x"], v2["y"] - v1["y"])
            bearing = geometry.get_angle((v1["x"], v1["y"]), (v2["x"], v2["y"]))
            segments.append({
                "start_vertex_index": i,
                "end_vertex_index": (i + 1) % len(vertices),
                "length_meters": round(length, 2),
                "bearing": round(bearing, 1)
            })

        levels_parts = [p.strip() for p in (levels or "").split(",") if p.strip()]
        parcel_info = {
            "plot_no": plot_no,
            "plot_id": geom_json.get("plot_id", ""),
            "khata_no": geom_json.get("khata_no", ""),
            "pniu": geom_json.get("pniu", ""),
            "area": metrics["area_sqm"],
            "perimeter": metrics["perimeter_m"],
            "lat": poly_gps.centroid.y,
            "lon": poly_gps.centroid.x,
            "district": levels_parts[0] if len(levels_parts) > 0 else "",
            "subdivision": levels_parts[1] if len(levels_parts) > 1 else "",
            "circle": levels_parts[2] if len(levels_parts) > 2 else "",
            "mouza": levels_parts[3] if len(levels_parts) > 3 else "",
            "survey": levels_parts[4] if len(levels_parts) > 4 else "",
            "mapinst": levels_parts[5] if len(levels_parts) > 5 else "",
            "sheet_no": levels_parts[6] if len(levels_parts) > 6 else "",
            "owner_names": []
        }

        # Save to SQLite data/app.db
        p_id = cache.save_parcel(parcel_info, vertices, segments, geometry_wkt=poly_gps.wkt)
        parcel_info["id"] = p_id

        return {
            "success": True,
            "cached": False,
            "parcel": parcel_info,
            "vertices": vertices,
            "segments": segments,
            "report": None
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to parse parcel geometry: {e}"}, 500


def proxy_wms_tile(args):
    """
    Proxies WMS GetMap tile requests with 2-tier caching:
    Tier 1: In-memory LRU dict
    Tier 2: Disk cache (static/wms_cache/*.png)
    """
    key_str = "&".join(f"{k}={v}" for k, v in sorted(args.items()))
    cache_hash = hashlib.md5(key_str.encode("utf-8")).hexdigest()
    tile_filename = f"{cache_hash}.png"
    disk_path = os.path.join(WMS_CACHE_DIR, tile_filename)

    if cache_hash in _TILE_MEMORY_CACHE:
        return _TILE_MEMORY_CACHE[cache_hash], 200

    if os.path.exists(disk_path):
        with open(disk_path, "rb") as f:
            content = f.read()
            _TILE_MEMORY_CACHE[cache_hash] = content
            return content, 200

    url = f"{STATE_CONFIG['bhunaksha_url']}/wms"
    try:
        r = session.get(url, params=args, timeout=8)
        if r.status_code == 200 and r.content[:4] in (b"\x89PNG", b"GIF8"):
            with open(disk_path, "wb") as f:
                f.write(r.content)
            _TILE_MEMORY_CACHE[cache_hash] = r.content
            return r.content, 200
    except Exception:
        pass

    # Return empty 1x1 transparent PNG fallback
    transparent_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    return transparent_png, 200
