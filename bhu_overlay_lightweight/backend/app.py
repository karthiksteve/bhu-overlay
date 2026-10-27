import os
import sys

# Forward to canonical root app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting Bhu-Overlay API Server on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
