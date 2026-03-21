"""
conftest.py — Shared pytest configuration for GhostBackup backend tests.

Adds the backend/ directory to sys.path so all test modules can import
backend modules directly without package installation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
