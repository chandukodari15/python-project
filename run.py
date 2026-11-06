"""
WattWise Launcher
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print("=" * 65)
    print(" WattWise: Electricity Consumption Analysis System")
    print(f" Web Interface starting at: http://127.0.0.1:{port}")
    print("=" * 65)
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
