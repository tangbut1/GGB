import os
import re
import time
import json
import uuid
import threading
import requests
import yaml
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_socketio import SocketIO
from flask_cors import CORS
from src.forum.log_manager import LogManager
from src.forum.monitor import ForumMonitor
from src.forum.llm_host import validate_endpoint
from src.net_safety import safe_output_path
from src.agents.stepfun_agent import StepFunAgent
from src.knowledge.task_store import TaskStore
from src.knowledge.project_memory import (
    ProjectMemoryStore,
    build_memory_context,
)
from src.agents.orchestrator import OrchestratorAgent, ROLE_MAP, TURN_LABELS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'marketpulse-secret-key-change-me')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', max_http_buffer_size=10000000)


def _json_safe(value):
    """把分析数据递归转换成可 JSON 序列化的形式。

    Prophet/pandas 的时间戳（pd.Timestamp）和 numpy 标量会随预测结果
    进入 analysis_data，socketio.emit 时直接抛 TypeError，导致终态
    事件发不出、后台线程崩掉。这里统一转成字符串/浮点数。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:  # noqa: BLE001
            return str(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:  # noqa: BLE001
            return str(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


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

# 任务注册表落盘。tasks / task_history 都是内存结构，后端一重启历史就全丢，
# 左侧"分析记录"退回"暂无分析记录"，用户会以为任务丢了。TaskStore 每个任务
# 一个 JSON 文件，启动时从这里把列表恢复回来。
# 默认路径锚在项目根而不是 CWD——和 LogManager 一致，从任何目录启动都落在
# 同一个位置，否则换个目录跑就会读到一份空历史。
_PROJECT_ROOT = Path(__file__).resolve().parent
TASK_STORE_DIR = os.environ.get(
    "MP_TASK_STORE_DIR",
    str(_PROJECT_ROOT / config.get("data", {}).get("tasks_dir", "data/tasks")),
)
task_store = TaskStore(TASK_STORE_DIR)

# 跨会话项目记忆。与 TaskStore 分工：TaskStore 记"这次分析的状态与完整
# 结果"（点历史记录能原样恢复那一场对话）；ProjectMemoryStore 记"这个主题
# 下跨多次分析沉淀了什么"（新分析开始前检索相关结论注入上下文）。
# 两者共用 data/ 目录，重启都不丢。
MEMORY_DB_PATH = os.environ.get(
    "MP_MEMORY_DB",
    str(_PROJECT_ROOT / "data" / "memory" / "project_memory.db"),
)
memory_store = ProjectMemoryStore(MEMORY_DB_PATH)


def _store_time(entry):
    """TaskStore 的 ISO 时间转成前端要的 'YYYY-MM-DD HH:MM:SS'。

    侧边栏取 time.split(' ')[1] 当时钟显示，格式不对就整串渲染出来。
    """
    raw = entry.get("updated_at") or entry.get("created_at") or ""
    return raw.replace("T", " ").split(".")[0][:19]


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat()


def _conversation_summary(analysis_data: dict) -> str:
    """一次分析的会话摘要：立场 + 样本口径 + 核心分歧。

    摘要会被后续分析检索到并注入 prompt，所以必须自包含——只写"看空"
    两个字，下一次分析读到它也不知道是因为什么看空。
    """
    verdict = analysis_data.get("verdict") or {}
    stance = {"negative": "看空", "positive": "看多", "neutral": "中性"}.get(
        verdict.get("stance"), verdict.get("stance") or "未裁定")
    total = analysis_data.get("total_news") or 0
    neg = analysis_data.get("negative_pct") or 0
    parts = [f"裁判立场{stance}", f"样本 {total} 条", f"负面占比 {neg}%"]
    if verdict.get("key_disagreements"):
        parts.append(f"核心分歧：{verdict['key_disagreements'][0][:80]}")
    return "；".join(parts)


def _extract_project_memories(
    project_id: str,
    conversation_id: str,
    task_id: str,
    analysis_data: dict,
) -> None:
    """从终裁里提炼值得跨会话保留的结论。

    只提炼裁判给出的结构化字段，不把整篇辩论文本塞进记忆——那会让
    记忆库迅速膨胀成历史原文的副本，检索时也失去"结论"的筛选价值。
    """
    verdict = analysis_data.get("verdict") or {}
    if not verdict:
        return

    stance_text = {"negative": "看空", "positive": "看多", "neutral": "中性"}.get(
        verdict.get("stance"), verdict.get("stance"))
    if stance_text:
        conf = verdict.get("confidence")
        conf_text = f"（置信度 {round(conf * 100)}%）" if isinstance(conf, (int, float)) else ""
        memory_store.remember(
            project_id,
            f"裁判立场：{stance_text}{conf_text}。"
            f"样本 {analysis_data.get('total_news') or 0} 条，"
            f"负面占比 {analysis_data.get('negative_pct') or 0}%。",
            kind="finding",
            status="confirmed",
            source_conv=conversation_id,
            source_task=task_id,
        )

    for item in (verdict.get("key_disagreements") or [])[:3]:
        memory_store.remember(
            project_id, f"核心分歧：{str(item)[:200]}",
            kind="risk", status="confirmed",
            source_conv=conversation_id, source_task=task_id,
        )
    # 双方最有力论据各留一条：下次分析时这是最快还原"上次争了什么"的线索
    for label, key in (("红方", "red_strongest"), ("蓝方", "blue_strongest")):
        text = str(verdict.get(key) or "").strip()
        if text:
            memory_store.remember(
                project_id, f"{label}最有力论据：{text[:200]}",
                kind="finding", status="confirmed",
                source_conv=conversation_id, source_task=task_id,
            )
    recommendation = str(verdict.get("recommendation") or "").strip()
    if recommendation:
        memory_store.remember(
            project_id, f"行动建议：{recommendation[:200]}",
            kind="decision", status="confirmed",
            source_conv=conversation_id, source_task=task_id,
        )


def _seed_history_from_store():
    """启动时从磁盘恢复任务列表。

    上次进程退出时仍标记 running 的任务，它的后台线程已经跟着进程一起消失，
    永远不会再写终态。不改写的话它会永远挂在"分析中"——白占历史一行，
    也会让 join 回放给出错误的等待预期。统一判为中断。

    前提是同一时刻只有一个后端进程在写这个目录。两个进程共用 store_dir 时
    （比如用不同 PORT 各起一个），后起的会把前一个正在跑的任务误判成中断。
    正常部署只有一个进程，端口也天然保证了这点。
    """
    stale = task_store.list_running()
    for task_id in stale:
        task_store.update_status(task_id, "error", error="后端进程重启，任务中断")
    if stale:
        print(f"[MarketPulse] {len(stale)} 个未完成的任务已标记为中断")

    # list_recent 是新的在前；task_history 沿用"旧在前、新在后"的追加顺序，
    # 前端再 reverse 成新的在前。顺序反了侧边栏会整体倒序。
    for entry in reversed(task_store.list_recent(50)):
        task_history.append({
            "task_id": entry.get("task_id"),
            "keyword": entry.get("keyword", ""),
            "status": entry.get("status", "error"),
            "time": _store_time(entry),
        })


_seed_history_from_store()


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

    # 不能只用 int(time.time())：它的分辨率是 1 秒，同一秒内发起的两次
    # 分析会拿到同一个 task_id，后一个任务覆盖 tasks 里的前一个，两条
    # 流水线还会同时往同一个论坛日志和房间写数据。加随机后缀保证唯一，
    # 时间前缀保留下来便于按启动顺序读日志。
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    # 合并所有上传文件为单一 CSV
    if not local_data_path and (local_data or local_data_raw or local_data_raw_files):
        import tempfile
        import base64
        import csv
        import io
        tmpdir = Path("data/uploads")
        tmpdir.mkdir(parents=True, exist_ok=True)
        # task_id 虽然由上面这行服务端生成、理论上不含路径分隔符，但拼进
        # 文件路径这一步不该靠"上游恰好安全"来保证。校验一次，将来若有人
        # 改成从请求里取 task_id，这里就是拦住目录穿越的那道闸。
        if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
            return jsonify({"error": "非法的 task_id"}), 400

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
            # task_id 虽由上面几行服务端生成，拼进文件名仍以 tmpdir 为基准
            # 收敛一次：分量含分隔符、是绝对路径或越界即拒绝。这样即使将来
            # 有人把 task_id 改成从请求里取，这里也已是拦住穿越的那道闸。
            tmp_path = safe_output_path(tmpdir, f"upload_{task_id}.csv")
            # 先在内存里拼好 CSV 再一次性落盘：DictWriter 需要文件对象，
            # 但"为了写而开一个文件"不该是绕过路径收敛的理由。
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_records)
            tmp_path.write_text(buf.getvalue(), encoding='utf-8')
            local_data_path = str(tmp_path)

    # 初始化论坛与协调者
    forum_manager = LogManager(task_id)
    monitor = ForumMonitor(forum_manager, config)
    src_mode = data.get('srcMode', 'news')

    # 跨会话项目记忆：keyword 即项目名，同一主题的多次分析归到同一项目。
    # 先检索再分析——把此前结论作为背景注入红蓝双方的 prompt，新分析才能
    # "接得上"上一次，而不是每次都从零开始。
    project_id = memory_store.ensure_project(keyword)
    conversation_id = memory_store.start_conversation(project_id, task_id, keyword)
    recall = memory_store.recall(project_id, keyword)
    memory_context = build_memory_context(recall)
    if memory_context:
        print(f"[MarketPulse] 注入项目记忆：{len(recall.get('memories', []))} 条结论 / "
              f"{len(recall.get('conversations', []))} 次历史分析")

    orchestrator = OrchestratorAgent(
        task_id=task_id,
        keyword=keyword,
        config=config,
        forum_manager=forum_manager,
        monitor=monitor,
        socketio=socketio,
        local_data_path=local_data_path if local_data_path else None,
        src_mode=src_mode,
        memory_context=memory_context,
    )

    tasks[task_id] = {
        "status": "running",
        "keyword": keyword,
        "local_data_path": local_data_path,
        "forum_manager": forum_manager,
        "orchestrator": orchestrator,
        "monitor": monitor,
        "result": None,
        "project_id": project_id,
        "conversation_id": conversation_id,
    }
    task_store.create(task_id, keyword, src_mode)

    started_at = time.time()

    # 后台线程执行分析
    def run_task():
        # 裁判（Host）已是流水线内的一等公民（立论→引导→反驳→终裁），
        # 不再启动后台 ForumMonitor，避免裁判发言重复。
        try:
            result = orchestrator.run_pipeline()
            if result.get("status") == "error":
                raise Exception(result.get("message", "管道执行失败"))
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["result"] = result

            # 提取分析数据，通过 SocketIO 发送给前端
            report_data = result.get("data", {}).get("report_data", {})
            sentiment_summary = report_data.get("sentiment_summary", {})
            trend_summary = report_data.get("trend_summary", {})
            trend_results = report_data.get("trend_results", {})

            analysis_data = _json_safe({
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
                # 趋势质量评级与预测窗口由 TrendAgent 给出（ Prophet 拟合 +
                # 样本量判断），前端要原样展示而不是只给一个方向词
                "trend_summary": {
                    "trend_direction": trend_summary.get("trend_direction", "neutral"),
                    "confidence": trend_summary.get("confidence", 0),
                    "data_quality": trend_summary.get("data_quality", "未知"),
                    "data_note": trend_summary.get("data_note", ""),
                    "forecast_window": trend_summary.get("forecast_window", 0),
                    "recommendation": trend_summary.get("recommendation", ""),
                    "model_type": trend_summary.get("model_type", "unknown"),
                    "data_points": trend_summary.get("data_points", 0),
                    # Prophet 降级到线性基线的原因（正常拟合时为空串）
                    "fallback_reason": trend_summary.get("fallback_reason", ""),
                    # 多维舆情指标（情绪指数/负面占比/极化/声量/信源多样性/
                    # 权威占比/低可信占比/关注度峰值/日期覆盖）+ 按天聚合的
                    # 真实序列。全部由本批样本算出，没有外部基准。
                    "indicators": trend_summary.get("indicators", {}),
                    # 至少 2 个有日期的不同日期才有资格谈"未来 N 天"
                    "forecast_feasible": bool(trend_summary.get("forecast_feasible", False)),
                },
                # 详情
                "predictions": trend_results.get("predictions", []),
                "analyzed_news": report_data.get("analyzed_news", []),
                "nodes": report_data.get("nodes", []),
                "edges": report_data.get("edges", []),
                "ai_insights": report_data.get("ai_insights", None),
                "collect_meta": report_data.get("collect_meta", {}),
                "forum_debate": report_data.get("forum_debate", []),
                "debate_cards": report_data.get("debate_cards", []),
                "final_report": report_data.get("final_report", None),
                "keywords": report_data.get("keywords", []),
                # 带 TF-IDF 权重与文档频率的热词。前端热词 Tab 直接用它画图，
                # 不再拿排名硬凑柱高。
                "keyword_weights": report_data.get("keyword_weights", []),
                # 情绪分布的方法论参数：LLM 校正是否生效、算法原值是多少。
                # 右侧"情感"Tab 要据此说明数字是怎么来的。
                "sentiment_summary": {
                    "positive_count": sentiment_summary.get("positive_count", 0),
                    "negative_count": sentiment_summary.get("negative_count", 0),
                    "neutral_count": sentiment_summary.get("neutral_count", 0),
                    "total_news": sentiment_summary.get("total_news", 0),
                    "avg_sentiment": sentiment_summary.get("avg_sentiment", 0),
                    "llm_corrected": bool(sentiment_summary.get("llm_corrected", False)),
                    "algo_positive_count": sentiment_summary.get("algo_positive_count", 0),
                    "algo_negative_count": sentiment_summary.get("algo_negative_count", 0),
                    "algo_neutral_count": sentiment_summary.get("algo_neutral_count", 0),
                },
                # 红蓝辩论裁判终裁
                "verdict": report_data.get("verdict", {}),
                # 研判卡：风险分/趋势方向/观察窗口/核心证据，由实测指标确定性
                # 算出。这是中间区域的默认主视图，不是辩论的附属说明。
                "verdict_card": report_data.get("verdict_card", {}),
                # 标记数据来源
                "from_backend": True
            })
            tasks[task_id]["analysis_data"] = analysis_data

            # 完整结果落盘：点击左侧历史记录要能原样恢复这一场对话
            # （发言 + 终裁 + 右侧五个 Tab 的数据），只能重新采集的话，
            # 拿到的已经是另一批数据了。
            debate_turns = []
            for msg in forum_manager.get_all_messages():
                turn = _to_debate_turn(msg)
                if turn:
                    debate_turns.append(turn)
            host_msgs = [m for m in forum_manager.get_all_messages() if m.get("agent") == "HOST"]
            for msg in host_msgs:
                debate_turns.append({
                    "author": "HOST",
                    "type": "AGENT",
                    "role": "judge",
                    "round": msg.get("round", 0),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp", ""),
                    "kind": "verdict",
                    "verdict": analysis_data.get("verdict"),
                })
            task_store.save_payload(task_id, {
                "task_id": task_id,
                "keyword": keyword,
                "project_id": project_id,
                "conversation_id": conversation_id,
                "completed_at": _store_time({"updated_at": _now_iso()}),
                "turns": debate_turns,
                "analysis_data": analysis_data,
            })

            # 项目记忆：发言原文 + 从终裁提炼的结论。原文保留以便回溯纠正，
            # 提炼结论供后续分析检索。
            memory_store.append_message(
                conversation_id, "user", keyword, "user", 0)
            for msg in forum_manager.get_all_messages():
                if msg.get("agent") in ("SYSTEM", None):
                    continue
                memory_store.append_message(
                    conversation_id,
                    "judge" if msg.get("agent") == "HOST" else "agent",
                    msg.get("content", ""),
                    msg.get("agent", ""),
                    msg.get("round", 0),
                )
            memory_store.finish_conversation(
                conversation_id,
                summary=_conversation_summary(analysis_data),
                status="completed",
            )
            _extract_project_memories(project_id, conversation_id, task_id, analysis_data)

            task_history.append({
                "task_id": task_id,
                "keyword": keyword,
                "status": "completed",
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            task_store.update_status(task_id, "completed")
            task_store.update_stats(task_id, {
                "duration_seconds": round(time.time() - started_at, 1),
                "total_news": analysis_data.get("total_news", 0),
            })
        except Exception as e:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["result"] = str(e)
            forum_manager.write("SYSTEM", 1, f"任务异常终止：{str(e)}")
            analysis_data = None
            # 失败的会话也要收尾：否则它永远挂在 running，项目下的会话列表
            # 会出现一条永不结束的记录，检索时也会被当成"进行中的分析"。
            try:
                memory_store.finish_conversation(
                    conversation_id, summary=f"分析失败：{str(e)[:120]}", status="error")
            except Exception:
                pass
            task_history.append({
                "task_id": task_id,
                "keyword": keyword,
                "status": "error",
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            task_store.update_status(task_id, "error", error=str(e))
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
    """SSE 端点 —— 针对已完成分析任务的流式追问。

    请求体：{"task_id": "...", "query": "...", "mode": "news"|"social",
             "insight": {...}(可选), "headline": "..."(可选)}
    若未提供 insight，则自动使用该任务的完整分析上下文。
    响应：SSE，每帧 {"chunk": "..."}，结束帧 [DONE]。
    """
    data = request.json or {}
    task_id = data.get('task_id', '')
    question = (data.get('query') or data.get('question') or '').strip()
    mode = data.get('mode', 'news')
    insight = data.get('insight') or {}
    headline = data.get('headline', '')

    if not question:
        return jsonify({"error": "query is required"}), 400

    # 从任务上下文自动补齐背景（前端只传 task_id + query 也能用）
    task = tasks.get(task_id)
    if task:
        ad = task.get("analysis_data") or {}
        headline = headline or ad.get("conclusion", "")
        verdict = ad.get("verdict") or {}
        if verdict:
            headline += f"\n裁判终裁：{verdict.get('stance', '')} {verdict.get('summary', '')}"
        insight = insight or {
            "title": ad.get("keyword", ""),
            "claim": headline,
            "evidence": f"负面 {ad.get('negative_pct', 0)}% / 正面 {ad.get('positive_pct', 0)}%，"
                        f"趋势 {ad.get('trend_direction', 'neutral')}",
        }

    mode_desc = (
        "社交媒体用户自发讨论（情绪驱动、碎片化）"
        if mode == "social"
        else "专业新闻媒体报道（机构视角、深度分析）"
    )

    system_prompt = (
        "你是一名顶级对冲基金的首席舆情分析师，正在回答用户对分析结论的追问。"
        "回答简洁有力，不超过150字，直接给出答案不废话。"
        "如果问题涉及投资建议，请声明风险提示。"
    )

    user_prompt = f"""数据源类型：{mode_desc}
背景分析结论：{headline or '（无）'}

用户关注的洞察：
- 标题：{insight.get('title', '')}
- 判断：{insight.get('claim', '')}
- 依据：{insight.get('evidence', '')}

用户追问：{question}"""

    def generate():
        # 优先用阶跃星辰 Agent：它的上下文窗口能吃下完整论坛记录和证据样本，
        # 追问经常是"蓝方的数据依据是什么"这种需要回原文的问题，小窗口模型
        # 只能看到结论看不到论据。Key 没配时自动回落到 forum_host 的配置。
        stepfun = StepFunAgent(config.get("agent_llm", {}).get("stepfun_agent", {}))
        if stepfun.available() and task:
            ad = task.get("analysis_data") or {}
            system_p, user_p = stepfun.build_followup_prompt(question, {
                "keyword": ad.get("keyword", ""),
                "conclusion": ad.get("conclusion", ""),
                "verdict": ad.get("verdict", {}),
                "sentiment_summary": ad.get("sentiment_summary", {}),
                "trend_summary": ad.get("trend_summary", {}),
                "analyzed_news": ad.get("analyzed_news", []),
            })
            answered = False
            for piece in stepfun.stream(system_p, user_p):
                if piece.startswith("Error"):
                    # 调用失败不当成答案吐给用户：整段改走 forum_host 兜底，
                    # 否则界面上会出现一句以 Error 开头的"回答"。
                    print(f"[MarketPulse] StepFun 追问失败，回落到 forum_host: {piece}")
                    break
                answered = True
                yield f"data: {json.dumps({'chunk': piece}, ensure_ascii=False)}\n\n"
            if answered:
                yield "data: [DONE]\n\n"
                return

        # ── 兜底：forum_host 的 LLM 配置（原路径）──
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
            try:
                endpoint = validate_endpoint(endpoint)
            except ValueError as e:
                yield f"data: {json.dumps({'error': f'端点校验失败: {e}'}, ensure_ascii=False)}\n\n"
                return

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
                stream=True,
                allow_redirects=False,
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


@app.route('/debate_followup', methods=['POST'])
def debate_followup():
    """追问触发新一轮红蓝辩论。

    与 /followup 的分工：/followup 是"让一个模型读结论然后回答"，
    快但只有一方的声音；这里是让红蓝双方就用户的追问各自复辩、再由裁判
    出补充裁定，慢一些但是辩论。

    请求体：{"task_id": "...", "query": "..."}
    响应：{"status": "success", "turns": [...], "verdict": {...}}

    辩论发言不走这个 HTTP 响应回传，而是通过 SocketIO 的 debate_turn /
    forum_message 实时推送（见 OrchestratorAgent.run_followup_debate），
    这样界面能和首轮辩论一样一条条冒出来，而不是等全部跑完一次性刷出。
    """
    data = request.json or {}
    task_id = data.get('task_id', '')
    question = (data.get('query') or data.get('question') or '').strip()

    if not question:
        return jsonify({"error": "query is required"}), 400

    task = tasks.get(task_id)
    if not task:
        return jsonify({
            "error": "任务不存在（服务可能已重启），请重新开始一次分析"
        }), 404
    if task.get("status") not in ("completed", "error"):
        return jsonify({"error": "分析尚未结束，暂不能追问"}), 409

    orchestrator = task.get("orchestrator")
    if not orchestrator:
        return jsonify({"error": "任务缺少分析上下文，无法追问"}), 500

    try:
        result = orchestrator.run_followup_debate(question)
    except Exception as e:  # noqa: BLE001
        forum_manager = task.get("forum_manager")
        if forum_manager:
            forum_manager.write("SYSTEM", 1, f"追问辩论异常：{e}")
        return jsonify({"error": f"追问辩论失败: {e}"}), 500

    if result.get("status") != "success":
        return jsonify({"error": result.get("message", "追问辩论失败")}), 500

    # 终裁变了，右侧"终裁"Tab 和分析数据要跟着更新
    new_verdict = result.get("verdict") or {}
    if new_verdict:
        task["analysis_data"] = task.get("analysis_data") or {}
        task["analysis_data"]["verdict"] = new_verdict
        socketio.emit('verdict_update', {
            'task_id': task_id, 'verdict': new_verdict
        }, room=task_id)

    return jsonify({
        "status": "success",
        "turns": result.get("turns", []),
        "verdict": new_verdict,
    })


@app.route('/status')
def api_status():
    """返回各 Agent 的 LLM 配置状态"""
    return jsonify({
        "agents": config_status,
        "all_configured": all_configured
    })

@app.route('/history')
def history():
    # 返回精简列表
    simplified = []
    for t in task_history[-50:]:
        simplified.append({
            "task_id": t.get("task_id"),
            "keyword": t.get("keyword"),
            "time": t.get("time"),
            "status": t.get("status")
        })
    return jsonify(simplified)

@app.route('/history/<task_id>')
def history_detail(task_id):
    for t in task_history:
        if t.get("task_id") == task_id:
            return jsonify(_session_detail(t))
    # 落在 50 条窗口外的老任务：task_history 只保留了最近 50 条，磁盘上还有。
    entry = task_store.get(task_id)
    if entry:
        return jsonify(_session_detail({
            "task_id": entry.get("task_id"),
            "keyword": entry.get("keyword", ""),
            "status": entry.get("status", "error"),
            "time": _store_time(entry),
        }))
    return jsonify({"error": "Not found"}), 404


@app.route('/history/<task_id>', methods=['DELETE'])
def history_delete(task_id):
    """删除一条历史对话：任务记录、完整结果、会话与发言。

    三处都要清掉，只删一处会留下能恢复出来的残影——侧边栏看不见，但
    /history/<id> 仍能取回 payload，或者项目记忆里还留着那段发言原文。

    正在运行的任务不删：删了任务文件，后台线程跑完还会再写回来，反而留下
    一个"已删除但状态是 completed"的僵尸记录。让用户先停或等它结束。
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
        return jsonify({"error": "非法的 task_id"}), 400

    if task_id in tasks and tasks[task_id].get("status") in ("running", "pending"):
        return jsonify({"error": "任务正在分析中，无法删除"}), 409

    removed = task_store.delete(task_id)
    memory_store.delete_conversation_by_task(task_id)
    # 内存里的两份也要同步：task_history 是 /history 的数据源，tasks 里若
    # 有残留条目会让 /status 与侧边栏继续显示这条已删除的记录。
    task_history[:] = [t for t in task_history if t.get("task_id") != task_id]
    tasks.pop(task_id, None)

    if not removed:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"deleted": task_id})


def _session_detail(base: dict) -> dict:
    """把一条历史记录补成"可完整恢复一场对话"的载荷。

    点击左侧历史记录时前端要的是那一次分析的**原始内容**：辩论发言、终裁、
    右侧五个 Tab 的数据。少了这些就只能重新采集，而重新采集是另一批数据，
    不是"那次分析"了。
    """
    task_id = base.get("task_id")
    payload = task_store.load_payload(task_id) if task_id else None
    out = dict(base)
    if not payload:
        out["restorable"] = False
        out["turns"] = []
        out["analysis_data"] = None
        return out

    out["restorable"] = True
    out["turns"] = _turns_from_payload(payload)
    out["analysis_data"] = payload.get("analysis_data")
    return out


def _turns_from_payload(payload: dict) -> list:
    """从落盘的分析结果重建前端辩论卡片流。

    顺序必须和实时观看时一致：用户提问 → 采集 → 红方/蓝方按轮次 → 裁判。
    直接用 debate_cards 的 round + priority 排序，与 ReportAgent 生成卡片
    时的排序同源，避免恢复出来的顺序和当场看到的不一样。
    """
    cards = payload.get("analysis_data", {}).get("debate_cards") or []
    if not cards:
        return []

    ordered = sorted(cards, key=lambda c: (c.get("round") or 0, c.get("priority", 9)))
    turns = []
    for card in ordered:
        agent = card.get("agent") or ""
        content = card.get("full_text") or card.get("rest_text") or card.get("summary") or ""
        if not content:
            continue
        role = ROLE_MAP.get(agent, "agent")
        turn = {
            "id": f"{agent}|{card.get('round') or 0}",
            "author": agent,
            "label": TURN_LABELS.get(role) or card.get("agent_label") or agent,
            "role": role,
            "round": card.get("round") or 0,
            "content": content,
            "kind": "agent",
        }
        if role == "judge":
            turn["kind"] = "verdict"
            turn["label"] = "裁判终裁"
        turns.append(turn)

    # 终裁的结构化字段挂到最后一条裁判发言上，和实时推送时一致
    verdict = payload.get("analysis_data", {}).get("verdict")
    if verdict and turns:
        for turn in reversed(turns):
            if turn["role"] == "judge":
                turn["verdict"] = verdict
                break
    return turns


# ── 跨会话项目记忆 API ─────────────────────────────────────────────────────

@app.route('/projects')
def api_projects():
    """项目列表。左栏按项目分组展示历史会话。"""
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50
    projects = memory_store.list_projects(limit=limit)
    # 附带每个项目的会话摘要，左栏展开项目时不必再发一次请求
    for p in projects:
        convs = memory_store.list_conversations(p["project_id"], limit=50)
        p["conversations"] = [
            {
                "conversation_id": c["conversation_id"],
                "task_id": c["task_id"],
                "keyword": c["keyword"],
                "title": c.get("title") or c["keyword"],
                "summary": c.get("summary") or "",
                "status": c.get("status"),
                "started_at": c.get("started_at"),
            }
            for c in convs
        ]
    return jsonify(projects)


@app.route('/projects/<project_id>')
def api_project_detail(project_id):
    project = memory_store.get_project(project_id)
    if not project:
        return jsonify({"error": "Not found"}), 404
    conversations = memory_store.list_conversations(project_id, limit=100)
    for c in conversations:
        c["messages"] = memory_store.get_messages(c["conversation_id"], limit=500)
    return jsonify({
        "project": project,
        "conversations": conversations,
        "memories": memory_store.list_memories(project_id, limit=100),
    })


@app.route('/projects/<project_id>/memories', methods=['POST'])
def api_add_memory(project_id):
    """手工追加一条项目记忆（用户自己确认的规则/决策）。"""
    if not memory_store.get_project(project_id):
        return jsonify({"error": "Not found"}), 404
    data = request.json or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    kind = data.get("kind") or "note"
    if kind not in ("decision", "finding", "risk", "rule", "note"):
        kind = "note"
    memory_id = memory_store.remember(
        project_id,
        content,
        kind=kind,
        status="confirmed",
        source_conv=data.get("source_conversation_id"),
        source_task=data.get("source_task_id"),
    )
    return jsonify({"memory_id": memory_id}), 201


@app.route('/memories/<memory_id>', methods=['DELETE'])
def api_retire_memory(memory_id):
    """停用一条记忆（过时或提炼错误）。软删除，保留来源以便对比。"""
    if not memory_store.retire_memory(memory_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"retired": memory_id})


@app.route('/recall')
def api_recall():
    """按项目检索相关记忆与历史会话。"""
    project_id = request.args.get("project_id", "")
    query = request.args.get("q", "")
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    result = memory_store.recall(project_id, query)
    result["context"] = build_memory_context(result)
    return jsonify(result)


@app.route('/memory/stats')
def api_memory_stats():
    return jsonify(memory_store.stats())


@socketio.on('join')
def on_join(data):
    task_id = data['task_id']
    from flask_socketio import join_room
    join_room(task_id)

    if task_id not in tasks:
        # 任务不在表里只有两种原因：id 从来没存在过，或者后端进程重启过
        # （tasks 是内存字典，重启即清空）。后者会让客户端一直等一个永远
        # 不会来的 task_complete，输入框永久禁用。必须明确告知失败。
        socketio.emit('task_complete', {
            'task_id': task_id,
            'status': 'error',
            'data': None,
            'message': '该分析任务已不存在（服务可能已重启），请重新开始',
        }, room=task_id)
        return

    task = tasks[task_id]
    msgs = task["forum_manager"].get_all_messages()

    # 回放该任务已有的论坛发言（SYSTEM/HOST 内部消息不推给前端）
    for msg in msgs:
        turn = _to_debate_turn(msg)
        if turn:
            socketio.emit('debate_turn', turn, room=task_id)

    # 回放裁判事件：threading 模式下只有 HTTP 长轮询，客户端会在轮询
    # 切换瞬间掉线，实时单发的 forum_message / task_complete 就此丢失。
    # 重连后重新 join 必须能补上，否则终裁和终态永远到不了前端。
    debate = getattr(task.get("orchestrator"), "debate", None) or {}
    verdict = debate.get("verdict")
    host_msgs = [m for m in msgs if m.get("agent") == "HOST"]
    for idx, msg in enumerate(host_msgs):
        is_verdict = verdict and idx == len(host_msgs) - 1
        payload = {
            "agent": "HOST", "role": "judge", "round": msg.get("round", 0),
            "content": msg.get("content", ""),
            "kind": "verdict" if is_verdict else "guidance",
        }
        if is_verdict:
            payload["verdict"] = verdict
        socketio.emit('forum_message', payload, room=task_id)

    # 任务已结束则补发终态，让重连的客户端拿到完整分析数据
    if task["status"] in ("completed", "error"):
        socketio.emit('task_complete', {
            'task_id': task_id,
            'status': task["status"],
            'data': task.get("analysis_data"),
        }, room=task_id)


def _to_debate_turn(msg: dict):
    """把论坛结构化消息转成前端辩论卡片所需的统一结构。

    返回 None 表示该消息不推送给前端（SYSTEM 内部日志 / HOST 裁判发言，
    后者由 forum_message 通道以更丰富的结构单独推送）。
    """
    agent = msg.get("agent", "")
    if agent in ("SYSTEM", "HOST") or not msg.get("content"):
        return None
    return {
        "author": agent,
        "type": "AGENT",
        "role": ROLE_MAP.get(agent, "agent"),
        "round": msg.get("round", 0),
        "content": msg.get("content", ""),
        "timestamp": msg.get("timestamp", ""),
    }


def background_log_emitter():
    """后台线程：每秒轮询各任务的结构化消息并广播增量，同时广播使用量统计"""
    last_processed = {}
    last_usage = {}
    while True:
        time.sleep(1)
        for task_id, task_info in list(tasks.items()):
            try:
                manager = task_info["forum_manager"]
                msgs = manager.get_all_messages()
                idx = last_processed.get(task_id, 0)
                if len(msgs) > idx:
                    for msg in msgs[idx:]:
                        turn = _to_debate_turn(msg)
                        if turn:
                            socketio.emit('debate_turn', turn, room=task_id)
                    last_processed[task_id] = len(msgs)

                # Emit usage stats if changed
                current_usage = manager.get_usage_stats()
                prev_usage = last_usage.get(task_id, {})
                if current_usage != prev_usage:
                    socketio.emit('api_usage_update', current_usage, room=task_id)
                    last_usage[task_id] = current_usage

            except Exception:
                pass


threading.Thread(target=background_log_emitter, daemon=True).start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    # debug=True 会拉起 watchdog reloader：流水线跑到一半时任何源码/.pyc 变动
    # 都会重启进程，把后台分析线程连同任务杀掉，前端再也收不到终态事件。
    # 需要热重载的调试场景请用 `flask run`，跑分析一律用这个入口。
    socketio.run(app, debug=False, port=port, allow_unsafe_werkzeug=True)
