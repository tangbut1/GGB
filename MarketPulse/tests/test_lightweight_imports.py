import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_core_agent_modules_import_without_optional_runtime_dependencies():
    import src.agents.base_agent  # noqa: F401
    import src.agents.collect_agent  # noqa: F401


if __name__ == "__main__":
    test_core_agent_modules_import_without_optional_runtime_dependencies()
