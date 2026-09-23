"""一次性连通性自检：确认 StepFun Key 与端点可用。

只打印 describe() 结果与一次极短补全的前若干字符，不落盘任何数据。

运行（在 MarketPulse/ 下）：
    python scripts/check_stepfun.py

退出码：0 正常；1 未配置 Key；2 调用返回错误。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.stepfun_agent import StepFunAgent  # noqa: E402
from src import config as cfg  # noqa: E402


def main() -> int:
    # app.py 在 import 时就调一次；独立脚本必须自己调，否则 .env 不加载
    cfg.init_config()
    agent = StepFunAgent({
        "base_url": cfg.agent_base_url("stepfun_agent"),
        "api_key": cfg.agent_api_key("stepfun_agent"),
        "model": cfg.agent_model("stepfun_agent"),
        "temperature": cfg.agent_temperature("stepfun_agent"),
        "timeout": cfg.agent_timeout("stepfun_agent"),
    })
    print("describe:", agent.describe())

    if not agent.available():
        print("未配置可用 Key，跳过调用")
        return 1

    reply = agent.complete(
        "你是一个简洁的中文助手。只用一句话回答。",
        "用一句话说明什么是舆情风险。",
        temperature=0.2,
    )
    print("reply[:200]:", reply[:200])
    if reply.startswith("Error"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
