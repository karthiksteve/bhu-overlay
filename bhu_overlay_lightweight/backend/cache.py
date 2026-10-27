"""
cache.py - Lightweight SQLite & Memory Caching Module for Bhu-Overlay
Manages persistent caching in data/app.db using standard library sqlite3.
No heavy ORM (Flask-SQLAlchemy) required.
"""

import os
import json
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")

# In-memory LRU / transient dictionary for high-frequency hits
_MEM_CACHE = {}


def get_db():
    """Return a configured sqlite3 connection with Row factory and foreign keys enabled."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db():
    """Initialize database tables and indexes."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_db()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS parcels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plot_id TEXT,
                plot_no TEXT NOT NULL,
                khata_no TEXT,
                pniu TEXT,
                area REAL,
                perimeter REAL,
                lat REAL,
                lon REAL,
                district TEXT,
                subdivision TEXT,
                circle TEXT,
                mouza TEXT,
                survey TEXT,
                mapinst TEXT,
                sheet_no TEXT,
                owner_names TEXT,
                geometry_wkt TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_parcels_plot_no ON parcels(plot_no);
            CREATE INDEX IF NOT EXISTS idx_parcels_lookup ON parcels(district, circle, mouza, sheet_no, plot_no);

            CREATE TABLE IF NOT EXISTS parcel_vertices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcel_id INTEGER NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
                x REAL NOT NULL,
                y REAL NOT NULL,
                lon REAL NOT NULL,
                lat REAL NOT NULL,
                sequence_order INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_vertex_parcel ON parcel_vertices(parcel_id, sequence_order);

            CREATE TABLE IF NOT EXISTS boundary_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcel_id INTEGER NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
                start_vertex_index INTEGER NOT NULL,
                end_vertex_index INTEGER NOT NULL,
                length_meters REAL NOT NULL,
                bearing REAL
            );

            CREATE INDEX IF NOT EXISTS idx_segment_parcel ON boundary_segments(parcel_id);

            CREATE TABLE IF NOT EXISTS ldm_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcel_id INTEGER NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
                report_url TEXT NOT NULL,
                filename TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_reports_parcel ON ldm_reports(parcel_id);

            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.close()


def get_cache(key):
    """Retrieve cached data by key. Checks in-memory cache first, then SQLite."""
    if key in _MEM_CACHE:
        return _MEM_CACHE[key]

    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM cache_entries WHERE key = ?", (key,)).fetchone()
        conn.close()
        if row:
            data = json.loads(row["value"])
            _MEM_CACHE[key] = data
            return data
    except Exception as e:
        print(f"[cache.py] Error reading cache key '{key}': {e}")
    return None


def set_cache(key, value):
    """Store data in cache. Updates both memory cache and SQLite."""
    _MEM_CACHE[key] = value
    try:
        val_str = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        conn = get_db()
        with conn:
            conn.execute(
                "INSERT INTO cache_entries (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, created_at=CURRENT_TIMESTAMP",
                (key, val_str)
            )
        conn.close()
    except Exception as e:
        print(f"[cache.py] Error setting cache key '{key}': {e}")


def get_parcel(plot_no, parcel_id=None):
    """
    Retrieve parcel data with its vertices, segments, and latest report.
    Returns a dict structure matching the API expectations.
    """
    if str(parcel_id).strip().lower() in ("", "none", "null", "undefined"):
        parcel_id = None

    conn = get_db()
    try:
        if parcel_id:
            row = conn.execute("SELECT * FROM parcels WHERE id = ?", (parcel_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM parcels WHERE plot_no = ? ORDER BY id DESC LIMIT 1",
                (str(plot_no),)
            ).fetchone()

        if not row:
            return None

        parcel_dict = dict(row)
        p_id = parcel_dict["id"]

        # Parse owner names if JSON
        try:
            if parcel_dict.get("owner_names"):
                parcel_dict["owner_names"] = json.loads(parcel_dict["owner_names"])
            else:
                parcel_dict["owner_names"] = []
        except Exception:
            parcel_dict["owner_names"] = [parcel_dict["owner_names"]]

        # Fetch vertices
        v_rows = conn.execute(
            "SELECT * FROM parcel_vertices WHERE parcel_id = ? ORDER BY sequence_order ASC",
            (p_id,)
        ).fetchall()
        vertices = [dict(v) for v in v_rows]

        # Fetch segments
        s_rows = conn.execute(
            "SELECT * FROM boundary_segments WHERE parcel_id = ? ORDER BY id ASC",
            (p_id,)
        ).fetchall()
        segments = [dict(s) for s in s_rows]

        # Fetch latest report
        r_row = conn.execute(
            "SELECT * FROM ldm_reports WHERE parcel_id = ? ORDER BY id DESC LIMIT 1",
            (p_id,)
        ).fetchone()
        report = dict(r_row) if r_row else None

        return {
            "parcel": parcel_dict,
            "vertices": vertices,
            "segments": segments,
            "report": report
        }
    finally:
        conn.close()


def save_parcel(parcel_info, vertices, segments=None, geometry_wkt=None):
    """
    Save or update a parcel, its vertices, and boundary segments atomically.
    Returns the parcel ID.
    """
    conn = get_db()
    try:
        with conn:
            owners_json = json.dumps(parcel_info.get("owner_names", [])) if isinstance(parcel_info.get("owner_names"), list) else parcel_info.get("owner_names", "")

            cur = conn.execute("""
                INSERT INTO parcels (
                    plot_id, plot_no, khata_no, pniu, area, perimeter, lat, lon,
                    district, subdivision, circle, mouza, survey, mapinst, sheet_no,
                    owner_names, geometry_wkt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                parcel_info.get("plot_id", ""),
                str(parcel_info.get("plot_no", "")),
                parcel_info.get("khata_no", ""),
                parcel_info.get("pniu", ""),
                parcel_info.get("area"),
                parcel_info.get("perimeter"),
                parcel_info.get("lat"),
                parcel_info.get("lon"),
                parcel_info.get("district", ""),
                parcel_info.get("subdivision", ""),
                parcel_info.get("circle", ""),
                parcel_info.get("mouza", ""),
                parcel_info.get("survey", ""),
                parcel_info.get("mapinst", ""),
                parcel_info.get("sheet_no", ""),
                owners_json,
                geometry_wkt
            ))
            parcel_id = cur.lastrowid

            if vertices:
                vertex_data = [
                    (parcel_id, v["x"], v["y"], v["lon"], v["lat"], idx)
                    for idx, v in enumerate(vertices)
                ]
                conn.executemany("""
                    INSERT INTO parcel_vertices (parcel_id, x, y, lon, lat, sequence_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, vertex_data)

            if segments:
                segment_data = [
                    (parcel_id, s["start_vertex_index"], s["end_vertex_index"], s["length_meters"], s.get("bearing", 0.0))
                    for s in segments
                ]
                conn.executemany("""
                    INSERT INTO boundary_segments (parcel_id, start_vertex_index, end_vertex_index, length_meters, bearing)
                    VALUES (?, ?, ?, ?, ?)
                """, segment_data)

            return parcel_id
    finally:
        conn.close()


def save_report(parcel_id, report_url, filename):
    """Record an LDM PDF report for a parcel."""
    conn = get_db()
    try:
        with conn:
            conn.execute("""
                INSERT INTO ldm_reports (parcel_id, report_url, filename)
                VALUES (?, ?, ?)
            """, (parcel_id, report_url, filename))
    finally:
        conn.close()
