import os
import re
import time
import json
import threading
import requests
import yaml
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_socketio import SocketIO
from src.forum.log_manager import LogManager
from src.forum.monitor import ForumMonitor
from src.agents.orchestrator import OrchestratorAgent

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'marketpulse-secret-key-change-me')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


def _load_dotenv():
    """加载 .env 文件到环境变量（无外部依赖）"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()


def _expand_env(value):
    """递归展开字符串中的 ${VAR} 环境变量引用"""
    if isinstance(value, str):
        def replacer(m):
            var_name = m.group(1)
            return os.environ.get(var_name, m.group(0))
        return re.sub(r'\$\{(\w+)\}', replacer, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config():
    config_path = Path(__file__).parent / "src" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config = _expand_env(config)
    # 环境变量直接覆盖 API Key、Model 和 Base URL
    for agent_key in config.get("agent_llm", {}):
        agent_cfg = config["agent_llm"][agent_key]
        
        # 1. API Key
        env_var = f"MP_{agent_key.upper()}_API_KEY"
        if os.environ.get(env_var):
            agent_cfg["api_key"] = os.environ[env_var]
            
        # 2. 全局 Base URL & Model 覆盖
        if os.environ.get("MP_GLOBAL_BASE_URL"):
            agent_cfg["base_url"] = os.environ["MP_GLOBAL_BASE_URL"]
        if os.environ.get("MP_GLOBAL_MODEL"):
            agent_cfg["model"] = os.environ["MP_GLOBAL_MODEL"]
            
        # 3. 针对单个 Agent 覆盖 (优先级更高)
        base_url_env = f"MP_{agent_key.upper()}_BASE_URL"
        if os.environ.get(base_url_env):
            agent_cfg["base_url"] = os.environ[base_url_env]
        model_env = f"MP_{agent_key.upper()}_MODEL"
        if os.environ.get(model_env):
            agent_cfg["model"] = os.environ[model_env]
            
    return config


config = load_config()

# 检测 API Key 配置状态
def _check_config_status():
    """返回各 Agent 的 API Key 配置状态"""
    status = {}
    for agent_key, agent_cfg in config.get("agent_llm", {}).items():
        key = agent_cfg.get("api_key", "")
        is_set = bool(key) and not key.startswith("${") and key not in ("", "your-api-key-here")
        status[agent_key] = {
            "model": agent_cfg.get("model", "unknown"),
            "base_url": agent_cfg.get("base_url", ""),
            "configured": is_set
        }
    return status

config_status = _check_config_status()
all_configured = all(v["configured"] for v in config_status.values())

if not all_configured:
    missing = [k for k, v in config_status.items() if not v["configured"]]
    print(f"[MarketPulse] ⚠ 以下 Agent 的 API Key 未配置，LLM 调用将返回占位结果: {', '.join(missing)}")
    print("[MarketPulse] 请在 .env 文件或环境变量中设置对应的 API Key。参考 .env.example。")

# 全局任务字典
tasks = {}
# 任务历史
task_history = []


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/report/<task_id>')
def get_report(task_id):
    report_path = os.path.join("results", "reports", f"{task_id}.html")
    if os.path.exists(report_path):
        return send_file(report_path)
    return "报告未找到或任务已失败。", 404


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json or {}
    keyword = data.get('keyword', '')
    local_data_path = data.get('local_data_path', '')
    local_data = data.get('local_data')  # 前端直接传来的 JSON 数组
    local_data_raw = data.get('local_data_raw')  # base64 编码的单文件
    local_data_raw_files = data.get('local_data_raw_files')  # base64 多文件列表
    local_data_filename = data.get('local_data_filename', 'uploaded')

    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400

    task_id = f"task_{int(time.time())}"

    # 合并所有上传文件为单一 CSV
    if not local_data_path and (local_data or local_data_raw or local_data_raw_files):
        import tempfile
        import base64
        import csv
        tmpdir = Path("data/uploads")
        tmpdir.mkdir(parents=True, exist_ok=True)

        all_records = []
        if isinstance(local_data, list):
            all_records.extend(local_data)

        # 处理 base64 文件（单个或多个）
        raw_files = local_data_raw_files or ([{"raw": local_data_raw, "filename": local_data_filename}] if local_data_raw else [])
        for rf in raw_files:
            try:
                raw = rf.get("raw", "")
                fname = rf.get("filename", "uploaded")
                ext = Path(fname).suffix.lower()
                raw_bytes = base64.b64decode(raw.split(',',1)[-1] if ',' in raw else raw)
                if ext in ('.csv', '.txt', '.tsv'):
                    text = raw_bytes.decode('utf-8', errors='replace')
                    sep = '\t' if ext == '.tsv' else ','
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if len(lines) >= 2:
                        headers = [h.strip().replace('"','') for h in lines[0].split(sep)]
                        for line in lines[1:]:
                            vals = [v.strip().replace('"','') for v in line.split(sep)]
                            if len(vals) >= len(headers):
                                rec = dict(zip(headers, vals))
                                rec['_source_file'] = fname
                                all_records.append(rec)
                elif ext in ('.xlsx', '.xls'):
                    import io
                    import pandas as pd
                    df = pd.read_excel(io.BytesIO(raw_bytes))
                    for _, row in df.iterrows():
                        rec = row.to_dict()
                        rec['_source_file'] = fname
                        all_records.append(rec)
                elif ext == '.json':
                    import json
                    jd = json.loads(raw_bytes.decode('utf-8'))
                    if not isinstance(jd, list): jd = [jd]
                    for item in jd:
                        item['_source_file'] = fname
                        all_records.append(item)
            except Exception as e:
                print(f"[MarketPulse] 解析文件 {fname} 失败: {e}")

        if all_records:
            # 收集所有字段名
            all_keys = []
            for r in all_records:
                for k in r:
                    if k not in all_keys:
                        all_keys.append(k)
            tmp_path = tmpdir / f"upload_{task_id}.csv"
            with open(tmp_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(all_records)
            local_data_path = str(tmp_path)

    # 初始化论坛与协调者
    forum_manager = LogManager(task_id)
    monitor = ForumMonitor(forum_manager, config)
    src_mode = data.get('srcMode', 'news')
    orchestrator = OrchestratorAgent(
        task_id=task_id,
        keyword=keyword,
        config=config,
        forum_manager=forum_manager,
        monitor=monitor,
        socketio=socketio,
        local_data_path=local_data_path if local_data_path else None,
        src_mode=src_mode
    )

    tasks[task_id] = {
        "status": "running",
        "keyword": keyword,
        "local_data_path": local_data_path,
        "forum_manager": forum_manager,
        "orchestrator": orchestrator,
        "monitor": monitor,
        "result": None
    }

    # 后台线程执行分析
    def run_task():
        monitor.start()
        try:
            result = orchestrator.run_pipeline()
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["result"] = result

            # 提取分析数据，通过 SocketIO 发送给前端
            report_data = result.get("data", {}).get("report_data", {})
            sentiment_summary = report_data.get("sentiment_summary", {})
            trend_summary = report_data.get("trend_summary", {})
            trend_results = report_data.get("trend_results", {})

            analysis_data = {
                "keyword": keyword,
                "conclusion": result.get("summary", ""),
                # 核心指标
                "positive_pct": round(sentiment_summary.get("positive_count", 0) / max(sentiment_summary.get("total_news", 1), 1) * 100, 1),
                "negative_pct": round(sentiment_summary.get("negative_count", 0) / max(sentiment_summary.get("total_news", 1), 1) * 100, 1),
                "neutral_pct": round(sentiment_summary.get("neutral_count", 0) / max(sentiment_summary.get("total_news", 1), 1) * 100, 1),
                "positive_count": sentiment_summary.get("positive_count", 0),
                "negative_count": sentiment_summary.get("negative_count", 0),
                "total_news": sentiment_summary.get("total_news", 0),
                "avg_sentiment": sentiment_summary.get("avg_sentiment", 0),
                # 趋势
                "trend_direction": trend_summary.get("trend_direction", "neutral"),
                "confidence": trend_summary.get("confidence", 0),
                # 详情
                "predictions": trend_results.get("predictions", []),
                "analyzed_news": report_data.get("analyzed_news", []),
                "nodes": report_data.get("nodes", []),
                "edges": report_data.get("edges", []),
                "ai_insights": report_data.get("ai_insights", None),
                "collect_meta": report_data.get("collect_meta", {}),
                "forum_debate": report_data.get("forum_debate", []),
                # 标记数据来源
                "from_backend": True
            }
            tasks[task_id]["analysis_data"] = analysis_data

            task_history.append({
                "task_id": task_id,
                "keyword": keyword,
                "status": "completed",
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["result"] = str(e)
            forum_manager.write("SYSTEM", 1, f"任务异常终止：{str(e)}")
            analysis_data = None
            task_history.append({
                "task_id": task_id,
                "keyword": keyword,
                "status": "error",
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        finally:
            monitor.stop()
            # 清理上传产生的临时 CSV，防止磁盘膨胀
            if local_data_path and local_data_path.startswith("data/uploads/"):
                try:
                    os.remove(local_data_path)
                except OSError:
                    pass
            socketio.emit('task_complete', {
                'task_id': task_id,
                'status': tasks[task_id]["status"],
                'data': analysis_data
            }, room=task_id)

    threading.Thread(target=run_task, daemon=True).start()

    return jsonify({"task_id": task_id})


@app.route('/stream/<task_id>')
def stream(task_id):
    """SSE 端点 —— 实时推送分析进度"""
    def event_stream():
        last_idx = 0
        while True:
            if task_id in tasks:
                t = tasks[task_id]
                # 推送日志增量
                lines = t["forum_manager"].read_all_lines()
                for line in lines[last_idx:]:
                    yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip()}, ensure_ascii=False)}\n\n"
                last_idx = len(lines)

                # 任务完成时推送结果
                if t["status"] in ("completed", "error"):
                    yield f"data: {json.dumps({'type': 'done', 'status': t['status'], 'task_id': task_id}, ensure_ascii=False)}\n\n"
                    break
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Task not found'}, ensure_ascii=False)}\n\n"
                break
            time.sleep(1)
    return Response(event_stream(), mimetype="text/event-stream")


@app.route('/followup', methods=['POST'])
def followup():
    """SSE 端点 —— AI 解读追问"""
    data = request.json
    insight = data.get('insight', {})
    question = data.get('question', '')
    context_headline = data.get('headline', '')
    mode = data.get('mode', 'news')

    mode_desc = (
        "社交媒体用户自发讨论（情绪驱动、碎片化）"
        if mode == "social"
        else "专业新闻媒体报道（机构视角、深度分析）"
    )

    system_prompt = (
        "你是一名顶级对冲基金的首席舆情分析师，正在回答用户对某条洞察的追问。"
        "回答简洁有力，不超过150字，直接给出答案不废话。"
        "如果问题涉及投资建议，请声明风险提示。"
    )

    user_prompt = f"""数据源类型：{mode_desc}
背景分析结论：{context_headline}

用户关注的洞察：
- 标题：{insight.get('title', '')}
- 判断：{insight.get('claim', '')}
- 依据：{insight.get('evidence', '')}

用户追问：{question}"""

    def generate():
        try:
            # 复用 forum_host 的 LLM 配置进行追问
            host_cfg = config.get("agent_llm", {}).get("forum_host", {})
            base_url = host_cfg.get("base_url", "https://api.openai.com/v1")
            api_key = host_cfg.get("api_key", "")
            model = host_cfg.get("model", "gpt-4o-mini")

            if not api_key:
                yield f"data: {json.dumps({'error': 'API Key 未配置'}, ensure_ascii=False)}\n\n"
                return

            endpoint = base_url.rstrip("/")
            if not endpoint.endswith("/chat/completions"):
                endpoint = f"{endpoint}/chat/completions"

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "stream": True
            }

            resp = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=60,
                stream=True
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    chunk_data = line_str[6:]
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(chunk_data)
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield f"data: {json.dumps({'chunk': content}, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        pass
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/status')
def api_status():
    """返回各 Agent 的 LLM 配置状态"""
    return jsonify({
        "agents": config_status,
        "all_configured": all_configured
    })

@app.route('/history')
def history():
    return jsonify(task_history[-50:])


@socketio.on('join')
def on_join(data):
    task_id = data['task_id']
    from flask_socketio import join_room
    join_room(task_id)

    # 发送已有日志
    if task_id in tasks:
        lines = tasks[task_id]["forum_manager"].read_all_lines()
        for line in lines:
            socketio.emit('log_line', {'line': line}, room=task_id)


def background_log_emitter():
    """后台线程：每秒轮询各任务日志并广播增量"""
    last_processed = {}
    while True:
        time.sleep(1)
        for task_id, task_info in list(tasks.items()):
            if task_info["status"] == "running":
                try:
                    lines = task_info["forum_manager"].read_all_lines()
                    idx = last_processed.get(task_id, 0)
                    if len(lines) > idx:
                        for line in lines[idx:]:
                            socketio.emit('log_line', {'line': line}, room=task_id)
                        last_processed[task_id] = len(lines)
                except Exception:
                    pass


threading.Thread(target=background_log_emitter, daemon=True).start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    socketio.run(app, debug=True, port=port, allow_unsafe_werkzeug=True)
