#!/usr/bin/env python3
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.pipeline_worker import main

if __name__ == "__main__":
    raise SystemExit(main())
