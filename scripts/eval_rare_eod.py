#!/usr/bin/env python3
"""Back-compat alias — the product metric is the movement screener."""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / "eval_move_screener.py"), run_name="__main__")
