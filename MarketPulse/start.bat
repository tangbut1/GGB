@echo off
echo 正在启动 MarketPulse (红蓝辩论版)...
rem FLASK_ENV=development 会启用 reloader，流水线跑到一半会被重启杀掉，
rem 所以不用 `flask run`，直接走 app.py 的入口（debug=False）。
python app.py
pause
