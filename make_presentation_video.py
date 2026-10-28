"""
make_presentation_video.py
Generates a broadcast-quality Full HD (1920x1080) presentation demo video
complete with cinematic panning, lower-third titles, live teleprompter subtitles,
and elapsed timers matching the 3-4 minute presentation script.
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    # Try common Windows TrueType fonts, fallback to default
    font_candidates = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\calibri.ttf",
    ]
    if bold:
        font_candidates = [
            "C:\\Windows\\Fonts\\segoeuib.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\calibrib.ttf",
        ] + font_candidates

    for fp in font_candidates:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()

def create_video():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    output_mp4 = os.path.join(root_dir, "bhu_overlay_presentation_demo.mp4")
    docs_output_mp4 = os.path.join(root_dir, "docs", "bhu_overlay_presentation_demo.mp4")

    width, height = 1920, 1080
    fps = 15  # 15 fps gives smooth motion while keeping file size and render time optimized

    scenes = [
        {
            "img": "bhu_01_dashboard_initial.png",
            "duration": 28,
            "part": "PART 1: PLATFORM OVERVIEW & MOTIVATION",
            "title": "Bhu-Overlay: AI-Augmented Cadastral GIS Platform",
            "sub": "Resolving agricultural land fragmentation and ocular chain survey disputes with automated GIS and AI.",
            "pan": "zoom_in"
        },
        {
            "img": "system_architecture.jpg",
            "duration": 34,
            "part": "PART 2: SYSTEM ARCHITECTURE & DATA PIPELINE",
            "title": "Modular Multi-Tier End-to-End Architecture",
            "sub": "Ingests BhuNaksha WMS & satellite basemaps via Flask REST API with local SQLite spatial caching.",
            "pan": "pan_down"
        },
        {
            "img": "bhu_10_location_dropdowns_cascaded.png",
            "duration": 22,
            "part": "PART 3: ADMINISTRATIVE LOCATION CASCADING",
            "title": "7-Tier Cascading Administrative Selector",
            "sub": "Dynamic streaming from District down to Mouza, Survey, Map, and Sheet with real-time vector overlay.",
            "pan": "zoom_in"
        },
        {
            "img": "bhu_02_parcel_selected_vector_map.png",
            "duration": 26,
            "part": "PART 4: PARCEL DEMARCATION & BOUNDARY INSPECTION",
            "title": "Plot 1623 Inspection: 43 Boundary Nodes & Side Lengths",
            "sub": "Exact polygon geometry with real-time segment measurements in meters (e.g. 27.3m, 14.8m) over satellite.",
            "pan": "pan_right"
        },
        {
            "img": "bhu_03_sidebar_measurements.png",
            "duration": 20,
            "part": "PART 5: REAL-TIME PARCEL METRICS & TOPOLOGY REPAIR",
            "title": "Survey Measurements: 8,624.5 m² (2.131 Acres)",
            "sub": "Automated zero-width buffer topology repair, perimeter evaluation (485.2m), and coordinate conversion.",
            "pan": "pan_down"
        },
        {
            "img": "bhu_04_kurra_subdivided_2shares.png",
            "duration": 28,
            "part": "PART 6: DETERMINISTIC KURRA EQUAL PARTITION (2-WAY)",
            "title": "Sub-20ms Bisection: Plot 1 (50.0%) & Plot 2 (50.0%)",
            "sub": "Swept-line bisection achieves strict area conservation (error < 0.001%) and Polsby-Popper score > 0.68.",
            "pan": "zoom_in"
        },
        {
            "img": "bhu_05_kurra_ai_explanation_panel.png",
            "duration": 26,
            "part": "PART 7: STATUTORY LLM ADVISORY REASONING",
            "title": "Google Gemini Legal Reasoning Under Revenue Code",
            "sub": "Codified evaluation under Sections 116-117 and Rule 109 compactness and road corridor accessibility.",
            "pan": "pan_down"
        },
        {
            "img": "bhu_06_kurra_3shares_custom.png",
            "duration": 24,
            "part": "PART 8: CUSTOM MULTI-SHARER ALLOCATION (50% / 25% / 25%)",
            "title": "Asymmetric Co-Tenancy Slicing & Micro-Assets",
            "sub": "Multi-plane slicing preserves contiguous bounds, equal road access, and tags field trees & wells.",
            "pan": "zoom_in"
        },
        {
            "img": "bhu_11_kurra_pdf_modal_viewer.png",
            "duration": 24,
            "part": "PART 9: OFFICIAL VECTOR PDF REPORT GENERATION",
            "title": "Native Vector Kurra Survey Report Modal Viewer",
            "sub": "Generates court-ready PDF with native Shapely vector drawings, allotment metrics, and legal decrees.",
            "pan": "pan_down"
        },
        {
            "img": "report_kurra_pdf_page1.png",
            "duration": 20,
            "part": "PART 10: STATUTORY SURVEY DECREE & DATA EXPORTS",
            "title": "Official Cadastral Partition Document & GIS Exports",
            "sub": "Tamper-evident visual Kurra survey for judicial filing, GeoJSON boundaries, and CSV coordinate exports.",
            "pan": "zoom_in"
        }
    ]

    total_seconds = sum(s["duration"] for s in scenes)
    print(f"[*] Compiling {len(scenes)} scenes into 1080p MP4 video...")
    print(f"[*] Total video duration: {total_seconds // 60}m {total_seconds % 60}s ({total_seconds} seconds)")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_mp4, fourcc, fps, (width, height))

    font_title = get_font(30, bold=True)
    font_part = get_font(20, bold=True)
    font_sub = get_font(22, bold=False)
    font_timer = get_font(24, bold=True)

    elapsed_frames = 0
    total_frames = total_seconds * fps

    for scene_idx, scene in enumerate(scenes):
        img_path = os.path.join(root_dir, scene["img"])
        if not os.path.exists(img_path):
            img_path = os.path.join(root_dir, "docs", "screenshots", scene["img"])
        if not os.path.exists(img_path):
            print(f"[!] Warning: Image not found: {scene['img']}, creating placeholder.")
            src_pil = Image.new("RGB", (1920, 1080), color=(20, 24, 33))
        else:
            src_pil = Image.open(img_path).convert("RGB")

        orig_w, orig_h = src_pil.size
        # Resize to fit canvas while preserving aspect ratio
        scale_base = min((width) / orig_w, (height - 130) / orig_h)
        base_w = int(orig_w * scale_base)
        base_h = int(orig_h * scale_base)
        resized_src = src_pil.resize((base_w, base_h), Image.Resampling.LANCZOS)

        scene_frames = scene["duration"] * fps

        for f in range(scene_frames):
            t = f / float(scene_frames)  # 0.0 to 1.0

            # Subtle cinematic motion (Ken Burns effect)
            if scene["pan"] == "zoom_in":
                zoom = 1.0 + 0.05 * t
            elif scene["pan"] == "pan_down":
                zoom = 1.03
            elif scene["pan"] == "pan_right":
                zoom = 1.0 + 0.04 * t
            else:
                zoom = 1.02

            cur_w = int(base_w * zoom)
            cur_h = int(base_h * zoom)
            zoomed = resized_src.resize((cur_w, cur_h), Image.Resampling.BILINEAR)

            # Center on canvas with slight pan offset
            frame_img = Image.new("RGB", (width, height), color=(14, 18, 26))

            if scene["pan"] == "pan_down":
                offset_y = int(30 - 40 * t)
            else:
                offset_y = 20

            if scene["pan"] == "pan_right":
                offset_x = int(30 - 50 * t)
            else:
                offset_x = 0

            paste_x = (width - cur_w) // 2 + offset_x
            paste_y = ((height - 140) - cur_h) // 2 + offset_y
            frame_img.paste(zoomed, (paste_x, paste_y))

            # Draw sleek Lower-Third Overlay Banner
            draw = ImageDraw.Draw(frame_img, "RGBA")
            # Gradient/Dark Banner at bottom
            draw.rectangle([(0, height - 145), (width, height)], fill=(12, 16, 24, 245))
            draw.line([(0, height - 145), (width, height - 145)], fill=(0, 200, 255, 200), width=3)

            # Header / Category Tag
            draw.text((45, height - 135), scene["part"].upper(), font=font_part, fill=(0, 210, 255))

            # Main Scene Title
            draw.text((45, height - 105), scene["title"], font=font_title, fill=(255, 255, 255))

            # Subtitle / Teleprompter Spoken Cue
            draw.text((45, height - 65), scene["sub"], font=font_sub, fill=(210, 220, 235))

            # Timer Readout (Bottom Right)
            cur_sec = int(elapsed_frames / fps)
            tot_sec = total_seconds
            timer_text = f"{cur_sec // 60:02d}:{cur_sec % 60:02d} / {tot_sec // 60:02d}:{tot_sec % 60:02d}"
            draw.text((width - 240, height - 125), timer_text, font=font_timer, fill=(255, 215, 0))

            # Progress Bar across bottom edge
            progress_w = int((elapsed_frames / float(total_frames)) * width)
            draw.rectangle([(0, height - 6), (width, height)], fill=(35, 45, 60))
            draw.rectangle([(0, height - 6), (progress_w, height)], fill=(0, 198, 255))

            # Convert PIL to BGR OpenCV frame
            frame_bgr = cv2.cvtColor(np.array(frame_img), cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)
            elapsed_frames += 1

        print(f"  [+] Rendered scene {scene_idx + 1}/{len(scenes)}: {scene['title'][:40]}... ({scene['duration']}s)")

    out.release()
    print(f"\n[OK] Video successfully created at: {output_mp4}")
    file_size_mb = os.path.getsize(output_mp4) / (1024 * 1024)
    print(f"[OK] File size: {file_size_mb:.2f} MB")

    # Copy to docs folder as well
    try:
        import shutil
        shutil.copyfile(output_mp4, docs_output_mp4)
        print(f"[OK] Copied to docs: {docs_output_mp4}")
    except Exception as e:
        print(f"[!] Note on docs copy: {e}")

if __name__ == "__main__":
    create_video()
