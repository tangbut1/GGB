#!/bin/bash
# 启动 MarketPulse Flask 后端

echo "正在启动 MarketPulse (BettaFish多智能体版)..."
export FLASK_APP=app.py
export FLASK_ENV=development
python3 -m flask run --host=0.0.0.0 --port=5050
