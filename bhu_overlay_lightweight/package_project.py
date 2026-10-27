#!/usr/bin/env python3
"""
Reproducible Source Packager for Bhu-Overlay
============================================
Creates a clean, lightweight distributable ZIP archive of the application.
Excludes:
  - Virtual environments (venv/, .venv/)
  - Git repository internals (.git/)
  - Python bytecode (__pycache__/, *.pyc)
  - Test caches (.pytest_cache/)
  - Secret files (backend/.env, .env)
  - Session cookies and ephemeral auth dumps
  - Local log files and debug outputs
  - Redundant tile caches

Usage:
  python package_project.py [--output dist/bhu_overlay_clean.zip]
"""
import os
import sys
import zipfile
import argparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

EXCLUDE_DIRS = {
    'venv', '.venv', 'env', 'ENV',
    '.git', '.pytest_cache', '__pycache__',
    'dist', '.idea', 'templates'
}

EXCLUDE_FILES = {
    '.env', 'session_cookies.json',
    'app_stderr.txt', 'app_stdout.txt', 'stderr.txt', 'stdout.txt',
    'pdf_text.txt', 'cv_detector.py', 'extract_area.py',
    'bhunaksha.db.bak'
}

EXCLUDE_EXTS = {
    '.pyc', '.pyo', '.pyd', '.log', '.tmp', '.bak'
}

def is_excluded(rel_path):
    parts = rel_path.replace('\\', '/').split('/')
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
        if p == 'static' and len(parts) > 2 and parts[1] == 'wms_cache' and parts[2].endswith('.png'):
            # Exclude individual tile cache png files to keep distributable small
            return True
        if p == 'reports' and len(parts) > 1 and parts[-1].endswith('.pdf'):
            return True

    filename = parts[-1]
    if filename in EXCLUDE_FILES:
        return True
    _, ext = os.path.splitext(filename)
    if ext.lower() in EXCLUDE_EXTS:
        return True
    if filename.endswith('.db') and 'data/app.db' not in rel_path.replace('\\', '/'):
        # Only retain the canonical data/app.db
        return True
    return False

def package(output_path=None):
    if not output_path:
        dist_dir = os.path.join(ROOT_DIR, "dist")
        os.makedirs(dist_dir, exist_ok=True)
        output_path = os.path.join(dist_dir, "bhu_overlay_clean.zip")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    print(f"Packaging Bhu-Overlay from: {ROOT_DIR}")
    print(f"Target archive: {output_path}")

    packed_count = 0
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ROOT_DIR):
            # Modify dirs in-place to avoid descending into excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            for f in files:
                abs_path = os.path.join(root, f)
                rel_path = os.path.relpath(abs_path, ROOT_DIR)
                
                if is_excluded(rel_path):
                    continue
                
                zf.write(abs_path, arcname=rel_path)
                packed_count += 1
                total_uncompressed_bytes += os.path.getsize(abs_path)

    zip_size = os.path.getsize(output_path)
    print("\n[SUCCESS] Package created successfully!")
    print(f"  Files packaged: {packed_count}")
    print(f"  Uncompressed size: {total_uncompressed_bytes / (1024 * 1024):.2f} MB")
    print(f"  Compressed ZIP size: {zip_size / (1024 * 1024):.2f} MB ({zip_size:,} bytes)")
    return output_path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create clean Bhu-Overlay distributable ZIP")
    parser.add_argument('--output', '-o', default=None, help="Destination ZIP filepath")
    args = parser.parse_args()
    package(args.output)
