"""自配模型注册表的行为约束。

这个模块是"用户自己填 Key 然后选一个模型来跑"的落点，所以测试集中在三件
容易出事的地方：Key 不能漏出接口、非法 base_url 要在保存时就拦掉、以及
"删掉正在用的那个模型"之后不能留下一个指向不存在条目的 active_id。
"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.model_registry import ModelRegistry, config_override

# 明显是占位符的串，不是任何真实凭据
FAKE_KEY = "unit-test-placeholder-key-not-a-credential"

VALID = {
    "name": "DeepSeek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": FAKE_KEY,
    "model": "deepseek-chat",
}


def make_registry(tmpdir):
    return ModelRegistry(os.path.join(tmpdir, "models.json"))


def test_upsert_then_list_masks_key():
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        reg.upsert(dict(VALID))

        listed = reg.list_models()
        assert len(listed) == 1
        assert listed[0]["api_key_masked"].endswith(FAKE_KEY[-4:])
        assert FAKE_KEY not in json.dumps(listed, ensure_ascii=False)
        assert listed[0]["has_api_key"] is True

        # 服务端内部取得到明文，否则选中的模型没法真的用
        assert reg.get(listed[0]["id"])["api_key"] == FAKE_KEY


def test_first_model_becomes_active():
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        saved = reg.upsert(dict(VALID))
        assert reg.active_id() == saved["id"]
        assert reg.get_active()["model"] == "deepseek-chat"


def test_update_without_key_keeps_old_key():
    """前端表单里 Key 是遮罩回显的，用户只改模型名时会把星号提交回来。

    把遮罩串存成新 Key 会让这个模型从此再也调不通，而且看不出原因。
    """
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        saved = reg.upsert(dict(VALID))
        masked = "*" * 12 + FAKE_KEY[-4:]
        reg.upsert({"id": saved["id"], "name": "DeepSeek V3",
                    "model": "deepseek-chat", "api_key": masked})
        assert reg.get(saved["id"])["api_key"] == FAKE_KEY
        assert reg.get(saved["id"])["name"] == "DeepSeek V3"


def test_private_base_url_rejected():
    """指向内网的 base_url 必须在保存时就拒掉。

    BaseAgent 调用时也会校验，但那时用户已经跑了一半分析才失败。这里提前
    拒，错误当场可见。
    """
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        for bad in ("http://127.0.0.1:8080/v1", "http://169.254.169.254/v1",
                    "http://[::1]:11434/v1", "ftp://example.com/v1"):
            with pytest.raises(ValueError):
                reg.upsert({**VALID, "base_url": bad})


def test_loopback_allowed_with_escape_hatch(monkeypatch):
    """本地 Ollama / vLLM 是合理配置，逃生口打开时环回应当放行。"""
    monkeypatch.setenv("MP_ALLOW_PRIVATE_LLM_ENDPOINTS", "1")
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        saved = reg.upsert({**VALID, "base_url": "http://127.0.0.1:11434/v1"})
        assert reg.get(saved["id"])["base_url"] == "http://127.0.0.1:11434/v1"


def test_missing_required_fields_rejected():
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        for field in ("name", "base_url", "api_key", "model"):
            payload = {k: v for k, v in VALID.items() if k != field}
            with pytest.raises(ValueError):
                reg.upsert(payload)


def test_delete_active_reassigns():
    """删掉当前选用的模型不能留下悬空的 active_id。

    留着的话每次请求都会静默回落到 config.yaml——用户换了模型却没反应，
    而且没有任何提示。
    """
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        first = reg.upsert(dict(VALID))
        second = reg.upsert({**VALID, "name": "Kimi", "model": "moonshot-v1"})

        reg.set_active(second["id"])
        reg.delete(second["id"])
        assert reg.active_id() == first["id"]

        reg.delete(first["id"])
        assert reg.active_id() is None
        assert reg.get_active() is None


def test_set_active_validates():
    with TemporaryDirectory() as tmpdir:
        reg = make_registry(tmpdir)
        with pytest.raises(ValueError):
            reg.set_active("does-not-exist")
        reg.upsert(dict(VALID))
        reg.set_active(None)
        assert reg.active_id() is None


def test_config_override_shape():
    override = config_override({"base_url": "https://x/v1", "api_key": "k",
                                "model": "m", "temperature": 0.3,
                                "timeout": 200, "max_retries": 3, "junk": 1})
    assert set(override) == {"base_url", "api_key", "model",
                             "temperature", "timeout", "max_retries"}
    assert override["timeout"] == 200


def test_survives_reload():
    """落盘之后要能读回来。损坏的文件不能让新实例抛异常或凭空造出模型。"""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "models.json"
        reg = ModelRegistry(str(path))
        saved = reg.upsert(dict(VALID))
        reg.set_active(saved["id"])

        reg2 = ModelRegistry(str(path))
        assert len(reg2.list_models()) == 1
        assert reg2.active_id() == saved["id"]

        path.write_text("{ this is not valid json", encoding="utf-8")
        reg3 = ModelRegistry(str(path))
        assert reg3.list_models() == []
        assert reg3.active_id() is None
