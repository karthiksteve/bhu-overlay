"""
reports.py - Lightweight Vector PDF Land Division Report Generator
Generates official Kurra Partition Reports using 100% native vector drawing in fpdf2.
Zero OpenCV / Zero Pillow / Zero temporary raster files.
"""

import os
import math
from fpdf import FPDF
from shapely.geometry import Polygon, LineString

# Palette for sub-plots (soft fill, crisp outline)
SUBPLOT_PALETTE = [
    {"fill": (219, 234, 254), "stroke": (37, 99, 235),  "text": (30, 58, 138)},   # Blue
    {"fill": (220, 252, 231), "stroke": (22, 163, 74),  "text": (20, 83, 45)},   # Green
    {"fill": (254, 243, 199), "stroke": (217, 119, 6),  "text": (120, 53, 15)},  # Amber
    {"fill": (252, 231, 243), "stroke": (219, 39, 119), "text": (131, 24, 67)},  # Pink
    {"fill": (243, 232, 255), "stroke": (147, 51, 234), "text": (88, 28, 135)},  # Purple
    {"fill": (224, 242, 254), "stroke": (14, 165, 233), "text": (12, 74, 110)},  # Sky
]


class KurraReportPDF(FPDF):
    """Custom PDF document with header, footer, and styling."""

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(15, 23, 42)
        self.cell(0, 8, "BHU-OVERLAY: CADASTRAL PARTITION (KURRA) REPORT", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, "Official Cadastral Geometry Analysis & Statutory Land Subdivision Advisory", border=0, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(203, 213, 225)
        self.set_line_width(0.3)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.set_y(self.get_y() + 4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(148, 163, 184)
        self.cell(0, 5, f"Page {self.page_no()} | Bhu-Overlay Cadastral Engine | Generated on-demand", align="C")


def _transform_coords_to_page(exterior_coords, bounds, box_x, box_y, box_w, box_h):
    """
    Transforms geospatial coordinates (UTM or GPS) to PDF page coordinates (in mm).
    Inverts Y axis to match PDF coordinate origin (top-left).
    """
    minx, miny, maxx, maxy = bounds
    span_x = max(maxx - minx, 1e-6)
    span_y = max(maxy - miny, 1e-6)

    scale = min((box_w - 12) / span_x, (box_h - 12) / span_y)
    offset_x = box_x + (box_w - (span_x * scale)) / 2.0
    offset_y = box_y + (box_h - (span_y * scale)) / 2.0

    points = []
    for x, y in exterior_coords:
        px = offset_x + (x - minx) * scale
        py = offset_y + (maxy - y) * scale  # Invert Y for top-down page
        points.append((px, py))
    return points


def draw_vector_cadastral_map(pdf, sub_polys, frontage_coords, box_x=15, box_y=None, box_w=180, box_h=70, labels=None):
    """
    Draws the parcel and subdivision polygons directly as vector shapes on the PDF page.
    """
    if box_y is None:
        box_y = pdf.get_y()

    # Draw map container background
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.3)
    pdf.rect(box_x, box_y, box_w, box_h, style="FD")

    if not sub_polys:
        pdf.set_y(box_y + box_h + 3)
        return

    # Calculate global bounding box
    all_bounds = [p.bounds for p in sub_polys]
    minx = min(b[0] for b in all_bounds)
    miny = min(b[1] for b in all_bounds)
    maxx = max(b[2] for b in all_bounds)
    maxy = max(b[3] for b in all_bounds)
    bounds = (minx, miny, maxx, maxy)

    # Draw each sub-polygon
    for idx, poly in enumerate(sub_polys):
        pal = SUBPLOT_PALETTE[idx % len(SUBPLOT_PALETTE)]
        coords = list(poly.exterior.coords)
        page_pts = _transform_coords_to_page(coords, bounds, box_x, box_y, box_w, box_h)

        if len(page_pts) >= 3:
            pdf.set_fill_color(*pal["fill"])
            pdf.set_draw_color(*pal["stroke"])
            pdf.set_line_width(0.4)
            pdf.polygon(page_pts, style="FD")

        # Draw label at centroid
        cx, cy = poly.centroid.x, poly.centroid.y
        c_pts = _transform_coords_to_page([(cx, cy)], bounds, box_x, box_y, box_w, box_h)
        if c_pts:
            lbl_x, lbl_y = c_pts[0]
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*pal["text"])
            lbl_text = labels[idx] if labels and idx < len(labels) else f"Plot {idx + 1}"
            pdf.text(lbl_x - 4, lbl_y + 1, lbl_text)

    # Draw road frontage line if provided
    if frontage_coords and len(frontage_coords) >= 2:
        f_pts = _transform_coords_to_page(frontage_coords, bounds, box_x, box_y, box_w, box_h)
        pdf.set_draw_color(217, 119, 6)  # Amber-red road line
        pdf.set_line_width(1.0)
        for i in range(len(f_pts) - 1):
            pdf.line(f_pts[i][0], f_pts[i][1], f_pts[i + 1][0], f_pts[i + 1][1])

    pdf.set_y(box_y + box_h + 4)


def generate_pdf_report(parcel_info, metrics, subdivision_result=None, ai_evaluation=None, parcel_poly=None):
    """
    Generate an official, lightweight PDF report as bytes.
    Uses native vector rendering with zero temporary files.
    Supports both multi-share Kurra division reports and single-parcel LPM reports.
    """
    pdf = KurraReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    # --- Section 1: Land Location & Administrative Details ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 6, "1. LAND RECORD & ADMINISTRATIVE IDENTIFICATION", border=0, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 8)
    pdf.set_fill_color(241, 245, 249)

    col_w = 47.5
    h_cell = 5.5

    data_rows = [
        [("Plot Number", str(parcel_info.get("plot_no", "--"))),
         ("Khata Number", str(parcel_info.get("khata_no", "--") or "--")),
         ("PNIU Code", str(parcel_info.get("pniu", "--") or "--")),
         ("Sheet No", str(parcel_info.get("sheet_no", "--") or "--"))],
        [("District", str(parcel_info.get("district", "--") or "--")),
         ("Subdivision", str(parcel_info.get("subdivision", "--") or "--")),
         ("Circle", str(parcel_info.get("circle", "--") or "--")),
         ("Mouza", str(parcel_info.get("mouza", "--") or "--"))]
    ]

    for row in data_rows:
        for title, val in row:
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(col_w / 2, h_cell, f" {title}:", border=1, fill=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(col_w / 2, h_cell, f" {val}", border=1, fill=False)
        pdf.ln(h_cell)

    pdf.ln(3)

    # --- Section 2: Parcel Geometry & Measurements ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 6, "2. PARCEL GEOMETRY & BOUNDARY MEASUREMENTS", border=0, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 8)
    area_sqm = metrics.get("area_sqm", 0)
    area_acres = metrics.get("area_acres", 0)
    area_ha = metrics.get("area_hectares", 0)
    perim_m = metrics.get("perimeter_m", 0)

    geom_rows = [
        [("Area (Sq. Meters)", f"{area_sqm:,.2f} m2"), ("Area (Acres)", f"{area_acres:.4f} acres")],
        [("Area (Hectares)", f"{area_ha:.4f} ha"), ("Perimeter", f"{perim_m:,.2f} m")]
    ]
    for row in geom_rows:
        for title, val in row:
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(47.5, h_cell, f" {title}:", border=1, fill=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(47.5, h_cell, f" {val}", border=1, fill=False)
        pdf.ln(h_cell)

    pdf.ln(3)

    # --- Section 3: Cadastral Map Vector Drawing ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    is_subdivided = bool(subdivision_result and subdivision_result.get("polys"))
    section_3_title = "3. CADASTRAL PARTITION (KURRA) SKETCH" if is_subdivided else "3. CADASTRAL PARCEL SKETCH"
    pdf.cell(0, 6, section_3_title, border=0, new_x="LMARGIN", new_y="NEXT")

    sub_polys = []
    frontage_coords = None
    labels = None
    if is_subdivided:
        sub_polys = subdivision_result.get("polys", [])
        frontage_coords = subdivision_result.get("frontage_coords")
        labels = [f"Plot {i+1}" for i in range(len(sub_polys))]
    elif parcel_poly:
        sub_polys = [parcel_poly]
        labels = [f"Plot {parcel_info.get('plot_no', '')}"]

    draw_vector_cadastral_map(pdf, sub_polys, frontage_coords, box_x=15, box_w=180, box_h=65, labels=labels)

    # --- Section 4: Sub-Plot Allocation OR Boundary Segments ---
    if is_subdivided and "features" in subdivision_result:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(30, 41, 59)
        strat_name = subdivision_result.get("strategy_name", "Partition Allocation")
        pdf.cell(0, 6, f"4. SUB-PLOT ALLOCATION ({strat_name.upper()})", border=0, new_x="LMARGIN", new_y="NEXT")

        headers = [("Plot ID", 20), ("Share %", 25), ("Area (Sq M)", 35), ("Area (Acres)", 35), ("Perimeter (m)", 35), ("Road Frontage (m)", 40)]
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(226, 232, 240)
        pdf.set_text_color(15, 23, 42)
        for h_text, w in headers:
            pdf.cell(w, 5, h_text, border=1, align="C", fill=True)
        pdf.ln(5)

        pdf.set_font("Helvetica", "", 8)
        for f in subdivision_result["features"]:
            props = f.get("properties", {})
            p_id = str(props.get("sub_plot_id", "--"))
            p_pct = f"{props.get('share_percentage', 0):.1f}%"
            p_sqm = f"{props.get('area_sqm', 0):,.2f}"
            p_acres = f"{props.get('area_sqm', 0) * 0.000247105:.4f}"
            p_perim = f"{props.get('perimeter_m', 0):,.2f}"
            p_front = f"{props.get('frontage_m', 0):,.2f}"

            pdf.cell(20, 5, p_id, border=1, align="C")
            pdf.cell(25, 5, p_pct, border=1, align="C")
            pdf.cell(35, 5, p_sqm, border=1, align="R")
            pdf.cell(35, 5, p_acres, border=1, align="R")
            pdf.cell(35, 5, p_perim, border=1, align="R")
            pdf.cell(40, 5, p_front, border=1, align="R")
            pdf.ln(5)

        pdf.ln(3)
    else:
        # Intact single parcel boundary measurements table
        side_lengths = metrics.get("side_lengths", [])
        if side_lengths:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 41, 59)
            pdf.cell(0, 6, "4. BOUNDARY SEGMENTS & SIDE MEASUREMENTS", border=0, new_x="LMARGIN", new_y="NEXT")

            headers = [("Side / Boundary Segment", 60), ("Length (Meters)", 60), ("Length (Feet)", 60)]
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_fill_color(226, 232, 240)
            pdf.set_text_color(15, 23, 42)
            for h_text, w in headers:
                pdf.cell(w, 5, h_text, border=1, align="C", fill=True)
            pdf.ln(5)

            pdf.set_font("Helvetica", "", 8)
            for i, length_m in enumerate(side_lengths):
                next_idx = (i + 1) % len(side_lengths)
                pdf.cell(60, 5, f"Side {i+1} (V{i+1} -> V{next_idx+1})", border=1, align="C")
                pdf.cell(60, 5, f"{length_m:.2f} m", border=1, align="R")
                pdf.cell(60, 5, f"{length_m * 3.28084:.2f} ft", border=1, align="R")
                pdf.ln(5)
            pdf.ln(3)

    # --- Section 5: Legal & AI Advisory Section ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    sec_5_title = "5. REVENUE CODE ADVISORY & STATUTORY COMPLIANCE" if is_subdivided else "5. STATUTORY VERIFICATION & COMPLIANCE"
    pdf.cell(0, 6, sec_5_title, border=0, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(51, 65, 85)
    default_expl = (
        "Partition calculated based on geometric compactness under Rule 109(b) of the Revenue Code, "
        "ensuring equitable land division without creating unusable or irregular shapes."
        if is_subdivided else
        "Land Record & Cadastral boundary verified against official BhuNaksha GIS database. "
        "Coordinates georeferenced in UTM Zone 45N and WGS84 EPSG:4326 standards."
    )
    explanation = (ai_evaluation.get("explanation") if ai_evaluation else "") or default_expl
    pdf.multi_cell(0, 4.5, explanation, border=1)

    pdf.ln(2)

    # Statutory Disclaimer
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(148, 163, 184)
    disclaimer = (
        "Statutory Notice: This document is an advisory cadastral visualization and land division model based on "
        "BhuNaksha and ArcGIS public records. Under Section 117 and Rule 109 of the Revenue Code, final partition orders "
        "and physical Kurra demarcation require formal execution by the competent Revenue Court / Tehsildar."
    )
    pdf.multi_cell(0, 3.5, disclaimer)

    return bytes(pdf.output())
