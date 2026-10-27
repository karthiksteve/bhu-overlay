"""
geometry.py - Pure Python & Shapely Geometry and Land Subdivision Module
Performs deterministic calculations: area, perimeter, centroid, side lengths,
frontage, and multi-share Kurra subdivision with area conservation checks.
Zero OpenCV / Zero NumPy dependencies.
"""

import math
from shapely.geometry import Polygon, LineString, Point, MultiPolygon
from shapely.ops import split
import shapely.affinity
from shapely.validation import make_valid
import pyproj

# Cached pyproj Transformers (Singleton pattern prevents repeated SQLite disk lookups)
_TRANSFORMER_UTM_TO_GPS = None
_TRANSFORMER_GPS_TO_UTM = None


def get_utm_to_gps():
    """Singleton UTM Zone 45N (EPSG:32645) -> WGS84 GPS (EPSG:4326) transformer."""
    global _TRANSFORMER_UTM_TO_GPS
    if _TRANSFORMER_UTM_TO_GPS is None:
        _TRANSFORMER_UTM_TO_GPS = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)
    return _TRANSFORMER_UTM_TO_GPS


def get_gps_to_utm():
    """Singleton WGS84 GPS (EPSG:4326) -> UTM Zone 45N (EPSG:32645) transformer."""
    global _TRANSFORMER_GPS_TO_UTM
    if _TRANSFORMER_GPS_TO_UTM is None:
        _TRANSFORMER_GPS_TO_UTM = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
    return _TRANSFORMER_GPS_TO_UTM


def utm_to_gps(x, y):
    """Transform UTM x, y to GPS lon, lat."""
    return get_utm_to_gps().transform(x, y)


def gps_to_utm(lon, lat):
    """Transform GPS lon, lat to UTM x, y."""
    return get_gps_to_utm().transform(lon, lat)


def get_angle(p1, p2):
    """Calculate directional angle in degrees between two 2D points."""
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))


def ensure_valid_polygon(poly):
    """Ensure a Shapely polygon is valid and non-empty."""
    if not isinstance(poly, Polygon):
        raise ValueError("Geometry must be a Shapely Polygon")
    if not poly.is_valid:
        valid_geom = make_valid(poly)
        if isinstance(valid_geom, Polygon):
            poly = valid_geom
        elif isinstance(valid_geom, MultiPolygon):
            poly = max(valid_geom.geoms, key=lambda g: g.area)
        else:
            poly = poly.buffer(0)
    return poly


def calculate_polygon_metrics(poly):
    """
    Calculate area (sqm, acres, hectares), perimeter, and side lengths for a UTM polygon.
    """
    poly = ensure_valid_polygon(poly)
    area_sqm = poly.area
    perimeter_m = poly.length

    coords = list(poly.exterior.coords)
    side_lengths = []
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        side_lengths.append(round(length, 2))

    return {
        "area_sqm": round(area_sqm, 2),
        "area_acres": round(area_sqm * 0.000247105, 4),
        "area_hectares": round(area_sqm * 0.0001, 4),
        "perimeter_m": round(perimeter_m, 2),
        "centroid_utm": (poly.centroid.x, poly.centroid.y),
        "side_lengths": side_lengths
    }


def split_polygon_by_ratio(poly, target_ratio, angle_deg, tolerance=1e-4, max_iters=40):
    """
    Splits a polygon into two parts such that the first part has area = total_area * target_ratio.
    The splitting line is oriented at `angle_deg` (0 is horizontal).
    Uses a binary search approach with adaptive early convergence.
    """
    poly = ensure_valid_polygon(poly)
    if poly.is_empty or poly.area <= 0:
        return [poly]

    if target_ratio <= 0.001 or target_ratio >= 0.999:
        return [poly]

    target_area = poly.area * target_ratio

    # Translate poly to origin to avoid large coordinate numerical errors
    cx_poly, cy_poly = poly.centroid.x, poly.centroid.y
    poly_shifted = shapely.affinity.translate(poly, xoff=-cx_poly, yoff=-cy_poly)

    minx, miny, maxx, maxy = poly_shifted.bounds
    radius = math.hypot(maxx - minx, maxy - miny) * 2

    rad = math.radians(angle_deg)
    dx = math.cos(rad) * radius
    dy = math.sin(rad) * radius

    base_line = LineString([(-dx, -dy), (dx, dy)])

    sweep_rad = math.radians(angle_deg + 90)
    sweep_dx = math.cos(sweep_rad)
    sweep_dy = math.sin(sweep_rad)

    coords = list(poly_shifted.exterior.coords)
    projections = [c[0] * sweep_dx + c[1] * sweep_dy for c in coords]

    min_t = min(projections)
    max_t = max(projections)

    min_diff = float("inf")
    best_poly1 = None
    best_poly2 = None

    low = min_t
    high = max_t

    for _ in range(max_iters):
        mid = (low + high) / 2
        px = mid * sweep_dx
        py = mid * sweep_dy
        cut_line = shapely.affinity.translate(base_line, xoff=px, yoff=py)

        try:
            geometry_collection = split(poly_shifted, cut_line)
        except Exception:
            continue

        polygons = [geom for geom in geometry_collection.geoms if isinstance(geom, Polygon)]
        if len(polygons) < 2:
            if target_ratio < 0.5:
                high = mid
            else:
                low = mid
            continue

        p1 = None
        p2 = None
        for p in polygons:
            c = p.centroid
            proj = c.x * sweep_dx + c.y * sweep_dy
            if proj < mid:
                p1 = p if p1 is None else p1.union(p)
            else:
                p2 = p if p2 is None else p2.union(p)

        if p1 is None or p2 is None:
            polygons.sort(key=lambda p: p.centroid.x * sweep_dx + p.centroid.y * sweep_dy)
            p1 = polygons[0]
            p2 = polygons[-1]

        area1 = p1.area
        diff = abs(area1 - target_area)
        if diff < min_diff:
            min_diff = diff
            best_poly1 = p1
            best_poly2 = p2

        if area1 < target_area:
            low = mid
        else:
            high = mid
            if target_area > 0 and abs(area1 - target_area) / target_area < tolerance:
                break

    if best_poly1 is None or best_poly2 is None:
        return [poly]

    if not isinstance(best_poly1, Polygon) and hasattr(best_poly1, "geoms"):
        best_poly1 = max(best_poly1.geoms, key=lambda g: g.area)
    if not isinstance(best_poly2, Polygon) and hasattr(best_poly2, "geoms"):
        best_poly2 = max(best_poly2.geoms, key=lambda g: g.area)

    best_poly1 = shapely.affinity.translate(best_poly1, xoff=cx_poly, yoff=cy_poly)
    best_poly2 = shapely.affinity.translate(best_poly2, xoff=cx_poly, yoff=cy_poly)

    return [best_poly1, best_poly2]


def generate_strategies(poly, shares, frontage_coords=None, river_coords=None):
    """
    Generates 2 to 4 deterministic land subdivision strategies.
    Strictly verifies area conservation: sum(subplot_areas) ≈ original_area (within 0.5% tolerance).
    """
    poly = ensure_valid_polygon(poly)
    original_area = poly.area

    # Parse and normalize input shares
    parsed_shares = []
    for s in (shares or []):
        if isinstance(s, dict):
            val = s.get("fraction") or s.get("percentage") or s.get("share") or s.get("ratio") or 0.0
            parsed_shares.append(float(val))
        else:
            parsed_shares.append(float(s))

    if not parsed_shares or any(s <= 0 for s in parsed_shares):
        raise ValueError("Shares must be a non-empty list of positive numbers.")

    total_shares = sum(parsed_shares)
    normalized_shares = [s / total_shares for s in parsed_shares]

    rect = poly.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    d1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    d2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])

    longest_axis_angle = get_angle(coords[0], coords[1]) if d1 > d2 else get_angle(coords[1], coords[2])
    shortest_axis_angle = get_angle(coords[1], coords[2]) if d1 > d2 else get_angle(coords[0], coords[1])

    def run_split(angle_deg):
        result_polys = []
        current_poly = poly
        remaining_share = 1.0

        for i in range(len(normalized_shares) - 1):
            target_ratio = normalized_shares[i] / remaining_share
            parts = split_polygon_by_ratio(current_poly, target_ratio, angle_deg)
            if not parts or len(parts) < 2:
                break
            result_polys.append(parts[0])
            current_poly = parts[1]
            remaining_share -= normalized_shares[i]

        result_polys.append(current_poly)
        return result_polys

    raw_strategies = []

    # Strategy 1: Compact Cut (Parallel to Shortest Side)
    s1_polys = run_split(shortest_axis_angle)
    if len(s1_polys) == len(parsed_shares):
        raw_strategies.append({"name": "Compact Cut (Parallel to Shortest Side)", "polys": s1_polys, "angle": shortest_axis_angle})

    # Strategy 2: Longitudinal Cut (Parallel to Longest Side)
    s2_polys = run_split(longest_axis_angle)
    if len(s2_polys) == len(parsed_shares):
        raw_strategies.append({"name": "Longitudinal Cut (Parallel to Longest Side)", "polys": s2_polys, "angle": longest_axis_angle})

    # Strategy 3: Road Access Cut (Perpendicular to Road)
    if frontage_coords and len(frontage_coords) >= 2:
        front_angle = get_angle(frontage_coords[0], frontage_coords[-1])
        cut_angle = front_angle + 90
        s3_polys = run_split(cut_angle)
        if len(s3_polys) == len(parsed_shares):
            raw_strategies.append({"name": "Road Access Cut (Perpendicular to Road)", "polys": s3_polys, "angle": cut_angle})

    # Strategy 4: River Access Cut (Perpendicular to River)
    if river_coords and len(river_coords) >= 2:
        river_angle = get_angle(river_coords[0], river_coords[-1])
        cut_angle = river_angle + 90
        s4_polys = run_split(cut_angle)
        if len(s4_polys) == len(parsed_shares):
            raw_strategies.append({"name": "River Access Cut (Perpendicular to River)", "polys": s4_polys, "angle": cut_angle})

    # Fallback angles if primary strategies didn't generate enough valid strategies
    if len(raw_strategies) < 2:
        for fallback_angle in [0.0, 45.0, 90.0, 135.0, 30.0, 60.0]:
            f_polys = run_split(fallback_angle)
            if len(f_polys) == len(parsed_shares):
                raw_strategies.append({
                    "name": f"Directional Cut ({int(fallback_angle)}°)",
                    "polys": f_polys,
                    "angle": fallback_angle
                })
            if len(raw_strategies) >= 3:
                break

    # Filter duplicate strategies by angle similarity (within 5 degrees)
    unique_strategies = []
    seen_angles = []
    area_tolerance = 0.005 * original_area  # 0.5% area conservation tolerance

    for strat in raw_strategies:
        # Strict area conservation validation
        total_sub_area = sum(p.area for p in strat["polys"])
        if abs(total_sub_area - original_area) > area_tolerance:
            print(f"[geometry.py] Skipping strategy '{strat['name']}': Area discrepancy {abs(total_sub_area - original_area):.2f} exceeds tolerance.")
            continue

        angle_mod = strat["angle"] % 180
        is_duplicate = False
        for sa in seen_angles:
            if abs(sa - angle_mod) < 5 or abs(sa - angle_mod) > 175:
                is_duplicate = True
                break

        if not is_duplicate:
            unique_strategies.append(strat)
            seen_angles.append(angle_mod)
        elif "Road" in strat["name"]:
            for u in unique_strategies:
                if abs(u["angle"] % 180 - angle_mod) < 5 or abs(u["angle"] % 180 - angle_mod) > 175:
                    if "Road" not in u["name"]:
                        u["name"] += " / Road Access Cut"
                    break

    return unique_strategies
