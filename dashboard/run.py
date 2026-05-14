#!/usr/bin/env python3
"""Start the Pipeline Control Center dashboard.
Run from project root: python dashboard/run.py
"""
import os
import sys
import uvicorn

# Ensure project root is on path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

if __name__ == "__main__":
    # Change to project root so uvicorn can find the dashboard module
    os.chdir(_PROJECT_ROOT)
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[os.path.join(_PROJECT_ROOT, "dashboard")],
        log_level="info",
    )
