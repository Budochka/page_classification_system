#!/usr/bin/env python3
"""Convenience script to run the page classification system."""

import sys
from pathlib import Path

# Ensure src is on path when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from page_classification.main import main

if __name__ == "__main__":
    sys.exit(main())
