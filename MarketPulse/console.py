#!/usr/bin/env python3
"""MarketPulse Console Workstation — 多智能体市场舆情分析控制台。

Usage:
    python3 console.py
"""

import os
import sys

# Ensure the MarketPulse package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli.app import MarketPulseApp


if __name__ == "__main__":
    app = MarketPulseApp()
    app.run()
