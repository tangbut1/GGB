"""跨测试文件共用的隔离装置。

这里只有一个用途：**别让测试写进用户真实的库**。

``/analyze`` 是一条完整的写入路径——``ensure_project`` 建项目、
``start_conversation`` 开会话、``append_message`` 存每段发言、
``finish_conversation`` 收尾。测试里那些打 ``/analyze`` 的用例
（socket 契约、任务落盘）起的又是真的 Flask app，所以只要不隔离，
跑一遍 pytest，用户侧边栏里就会多出"落盘测试""契约测试""失败测试"
这几条点开什么都没有的记录。

隔离点选在 ``flask_app.memory_store`` 这一个模块级引用上：路由里
全部通过它访问，改引用就能整体换库，不需要动任何业务代码。

``flask_app`` fixture 由各测试模块自行定义（作用域不同），这里只依赖
它，不重复定义——重复定义会让模块内那份悄悄覆盖掉共用的那份。
"""

import pytest


@pytest.fixture
def isolated_memory(flask_app, tmp_path):
    """把 app 的 memory_store 换成一个临时库，测试结束后自动恢复。"""
    from src.knowledge.project_memory import ProjectMemoryStore

    replacement = ProjectMemoryStore(str(tmp_path / "memory.db"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(flask_app, "memory_store", replacement)
        yield replacement
