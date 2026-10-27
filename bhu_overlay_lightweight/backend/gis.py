"""
gis.py - ArcGIS Querying & Spatial Feature Retrieval
Manages on-demand vector querying for roads, rivers, and spatial infrastructure.
Uses bounded concurrent threads, connection pooling, and in-memory LRU caching.
"""

import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from shapely.geometry import LineString
import urllib3

# State-configurable GIS services dictionary
STATE_CONFIG = {
    "code": "10",
    "name": "Bihar",
    "gis_base_url": "https://gisserver.bihar.gov.in/arcgis/rest/services"
}

SERVICES = {
    "NHRoads": f"{STATE_CONFIG['gis_base_url']}/RCD_DEPT/NHRoads/MapServer/0/query",
    "SHRoads": f"{STATE_CONFIG['gis_base_url']}/RCD_DEPT/SHRoads/MapServer/0/query",
    "MDR": f"{STATE_CONFIG['gis_base_url']}/RCD_DEPT/MDR/MapServer/0/query",
    "ROAD_BIHAR": f"{STATE_CONFIG['gis_base_url']}/RCD_DEPT/ROAD_BIHAR/MapServer/0/query",
    "Village_Road": f"{STATE_CONFIG['gis_base_url']}/RWD/Village_Road/MapServer/0/query",
    "Rivers": f"{STATE_CONFIG['gis_base_url']}/WATER_IRRIGATION/Rivers/MapServer/0/query",
    "Streams": f"{STATE_CONFIG['gis_base_url']}/WATER_IRRIGATION/IrrigationStreams/MapServer/0/query"
}

PRIORITY = {
    "NHRoads": 1,
    "SHRoads": 2,
    "MDR": 3,
    "ROAD_BIHAR": 4,
    "Village_Road": 5
}

# Determine TLS verification policy
VERIFY_SSL = os.environ.get("VERIFY_SSL", "0").lower() in ("1", "true", "yes")
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Shared HTTP session with connection pooling
_SESSION = requests.Session()
_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=1)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)

# In-memory bounding box cache: bbox_str -> dict(roads=[...], rivers=[...])
_BBOX_CACHE = {}
_MAX_CACHE_ENTRIES = 64


def query_service(bbox_str, url, timeout=4.0):
    """Query a single ArcGIS REST query endpoint with bounded timeout."""
    params = {
        "geometry": bbox_str,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
        "outSR": "4326",
        "f": "json",
        "outFields": "Road_Name,ROADNAME,Rd_Name,NAME,RIVER_NAME,StreamName,OBJECTID",
        "returnGeometry": "true"
    }
    try:
        r = _SESSION.get(url, params=params, verify=VERIFY_SSL, timeout=timeout)
        if r.status_code == 200:
            return r.json().get("features", [])
    except Exception:
        pass
    return []


def get_nearby_vector_features(parcel_polygon_gps):
    """
    Queries roads and rivers within a buffered bbox of the parcel in GPS coordinates.
    Executes service requests concurrently via ThreadPoolExecutor.
    Returns (roads_list, rivers_list).
    """
    bounds = parcel_polygon_gps.bounds  # (minx, miny, maxx, maxy)
    buf = 0.0005  # ~50m buffer in degrees
    minx = round(bounds[0] - buf, 5)
    miny = round(bounds[1] - buf, 5)
    maxx = round(bounds[2] + buf, 5)
    maxy = round(bounds[3] + buf, 5)
    bbox_str = f"{minx},{miny},{maxx},{maxy}"

    if bbox_str in _BBOX_CACHE:
        cached = _BBOX_CACHE[bbox_str]
        return cached["roads"], cached["rivers"]

    features_by_service = {}
    futures = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        for name, url in SERVICES.items():
            futures[executor.submit(query_service, bbox_str, url)] = name

        for future in as_completed(futures):
            service_name = futures[future]
            try:
                features_by_service[service_name] = future.result()
            except Exception:
                features_by_service[service_name] = []

    roads = []
    rivers = []

    for name, f_list in features_by_service.items():
        is_river = name in ("Rivers", "Streams")
        for feat in f_list:
            geom = feat.get("geometry", {})
            paths = geom.get("paths", [])
            attrs = feat.get("attributes", {})

            for path in paths:
                if len(path) >= 2:
                    ls = LineString(path)
                    dist_deg = parcel_polygon_gps.distance(ls)
                    dist_m = dist_deg * 111320.0  # Approx meters conversion

                    if is_river:
                        riv_name = attrs.get("RIVER_NAME") or attrs.get("StreamName") or attrs.get("NAME") or "Water Body"
                        rivers.append({
                            "name": riv_name,
                            "category": name,
                            "geometry": ls,
                            "distance_m": dist_m
                        })
                    else:
                        rd_name = attrs.get("Road_Name") or attrs.get("ROADNAME") or attrs.get("Rd_Name") or attrs.get("NAME") or "Local Road"
                        roads.append({
                            "name": rd_name,
                            "category": name,
                            "priority": PRIORITY.get(name, 99),
                            "geometry": ls,
                            "distance_m": dist_m
                        })

    roads.sort(key=lambda r: (r["priority"], r["distance_m"]))
    rivers.sort(key=lambda r: r["distance_m"])

    if len(_BBOX_CACHE) >= _MAX_CACHE_ENTRIES:
        oldest_key = next(iter(_BBOX_CACHE))
        _BBOX_CACHE.pop(oldest_key, None)

    _BBOX_CACHE[bbox_str] = {"roads": roads, "rivers": rivers}
    return roads, rivers
