"""
run_app.py - Python launcher for Bhu-Overlay
Auto-detects virtual environment, launches the Flask server, and opens the dashboard in the default browser.
"""

import os
import sys
import webbrowser
import subprocess
from pathlib import Path

def main():
    root_dir = Path(__file__).parent
    venv_py = root_dir / ".venv" / "Scripts" / "python.exe"
    py_cmd = str(venv_py) if venv_py.exists() else sys.executable

    print("=" * 65)
    print("    Bhu-Overlay - Bihar Cadastral Map & Satellite Dashboard")
    print("=" * 65)
    print("\n[*] Starting Flask server on http://127.0.0.1:5001...")

    webbrowser.open("http://127.0.0.1:5001")
    subprocess.run([py_cmd, "app.py"], cwd=str(root_dir))

if __name__ == "__main__":
    main()
