@echo off
echo 正在启动 MarketPulse (BettaFish多智能体版)...
set FLASK_APP=app.py
set FLASK_ENV=development
python -m flask run --host=0.0.0.0 --port=5050
pause
