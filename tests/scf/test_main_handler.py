"""SCF 云函数入口 main_handler 测试

测试纯函数逻辑,不依赖真实网络请求。
通过 monkeypatch 替换 httpx 与环境变量。
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# 直接加载独立文件(避免依赖 aap 包)
FUNCTION_SRC = Path(__file__).resolve().parents[2] / "src" / "aap" / "scf" / "function_src" / "main.py"


def _load_main_module():
    """以独立模块方式加载 function_src/main.py(不依赖 aap 包)"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("aap_scf_main", FUNCTION_SRC)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scf_main(monkeypatch):
    """加载 SCF main 模块并设置 SCF_SECRET 环境变量"""
    monkeypatch.setenv("SCF_SECRET", "test-secret-123")
    # 重新加载模块以应用环境变量
    module = _load_main_module()
    # 强制重新读取环境变量
    module.SCF_SECRET = "test-secret-123"
    return module


# ===== _parse_event 测试 =====


def test_parse_event_api_gateway_format(scf_main) -> None:
    """解析 API 网关触发器格式(body 为 JSON 字符串)"""
    payload = {"secret": "x", "method": "POST", "path": "/cgi-bin/test", "params": {}}
    event = {
        "httpMethod": "POST",
        "path": "/",
        "body": json.dumps(payload),
        "isBase64Encoded": False,
    }
    result = scf_main._parse_event(event)
    assert result == payload


def test_parse_event_body_is_dict(scf_main) -> None:
    """body 已是字典时直接返回"""
    payload = {"secret": "x", "method": "GET", "path": "/test"}
    event = {"body": payload}
    result = scf_main._parse_event(event)
    assert result == payload


def test_parse_event_base64_encoded(scf_main) -> None:
    """body 为 base64 编码的 JSON"""
    payload = {"secret": "x", "method": "POST", "path": "/x"}
    body_str = json.dumps(payload)
    body_b64 = base64.b64encode(body_str.encode("utf-8")).decode("ascii")
    event = {"body": body_b64, "isBase64Encoded": True}
    result = scf_main._parse_event(event)
    assert result == payload


def test_parse_event_direct_call(scf_main) -> None:
    """直接调用格式(event 本身即载荷)"""
    payload = {"secret": "x", "method": "GET", "path": "/test"}
    result = scf_main._parse_event(payload)
    assert result == payload


def test_parse_event_invalid_json(scf_main) -> None:
    """body 非法 JSON 抛 ValueError"""
    event = {"body": "not-json{", "isBase64Encoded": False}
    with pytest.raises(ValueError, match="body 不是合法 JSON"):
        scf_main._parse_event(event)


def test_parse_event_not_dict(scf_main) -> None:
    """event 非字典抛 ValueError"""
    with pytest.raises(ValueError, match="event 必须是字典"):
        scf_main._parse_event("not a dict")  # type: ignore[arg-type]


def test_parse_event_unrecognized(scf_main) -> None:
    """无法识别的格式抛 ValueError"""
    with pytest.raises(ValueError, match="无法识别的事件格式"):
        scf_main._parse_event({"foo": "bar"})


# ===== main_handler 测试(不依赖真实网络) =====


def test_main_handler_secret_mismatch(scf_main, monkeypatch) -> None:
    """密钥不匹配返回 403"""
    monkeypatch.setenv("SCF_SECRET", "correct-secret")
    scf_main.SCF_SECRET = "correct-secret"
    event = {"body": json.dumps({
        "secret": "wrong-secret",
        "method": "POST",
        "path": "/cgi-bin/test",
    })}
    result = scf_main.main_handler(event, None)
    assert result["statusCode"] == 403
    assert "密钥验证失败" in result["body"]["error"]


def test_main_handler_secret_not_configured(scf_main, monkeypatch) -> None:
    """SCF_SECRET 未配置返回 500"""
    monkeypatch.delenv("SCF_SECRET", raising=False)
    scf_main.SCF_SECRET = ""
    event = {"body": json.dumps({
        "secret": "x", "method": "POST", "path": "/x",
    })}
    result = scf_main.main_handler(event, None)
    assert result["statusCode"] == 500
    assert "SCF_SECRET" in result["body"]["error"]


def test_main_handler_missing_path(scf_main) -> None:
    """缺少 path 参数返回 400"""
    event = {"body": json.dumps({
        "secret": "test-secret-123", "method": "POST", "path": "",
    })}
    result = scf_main.main_handler(event, None)
    assert result["statusCode"] == 400
    assert "path" in result["body"]["error"]


def test_main_handler_invalid_event_format(scf_main) -> None:
    """事件格式无法解析返回 400"""
    result = scf_main.main_handler({"foo": "bar"}, None)
    assert result["statusCode"] == 400
    assert "请求格式错误" in result["body"]["error"]


def test_main_handler_egress_ip_endpoint(scf_main) -> None:
    """/egress-ip 端点返回出口 IP"""
    with patch.object(scf_main, "get_egress_ip", return_value="1.2.3.4"):
        event = {"body": json.dumps({
            "secret": "test-secret-123",
            "method": "GET",
            "path": "/egress-ip",
        })}
        result = scf_main.main_handler(event, None)
    assert result["statusCode"] == 200
    assert result["body"]["body"]["ip"] == "1.2.3.4"


def test_main_handler_forward_json(scf_main) -> None:
    """转发 JSON 请求(通过 mock httpx)"""
    mock_resp = SimpleNamespace(
        status_code=200,
        text='{"errcode":0,"errmsg":"ok"}',
        json=lambda: {"errcode": 0, "errmsg": "ok"},
    )
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post = MagicMock(return_value=mock_resp)

    with patch.object(scf_main.httpx, "Client", return_value=mock_client):
        event = {"body": json.dumps({
            "secret": "test-secret-123",
            "method": "POST",
            "path": "/cgi-bin/draft/add",
            "params": {"access_token": "tok"},
            "body": {"articles": [{"title": "T"}]},
            "body_type": "json",
        })}
        result = scf_main.main_handler(event, None)

    assert result["statusCode"] == 200
    assert result["body"]["status_code"] == 200
    assert result["body"]["body"]["errcode"] == 0
    # 验证 httpx.post 被正确调用
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "api.weixin.qq.com/cgi-bin/draft/add" in str(call_args)


def test_main_handler_forward_multipart(scf_main) -> None:
    """转发 multipart 文件上传请求"""
    file_bytes = b"fake-image-data"
    file_b64 = base64.b64encode(file_bytes).decode("ascii")

    mock_resp = SimpleNamespace(
        status_code=200,
        text='{"media_id":"abc"}',
        json=lambda: {"media_id": "abc"},
    )
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post = MagicMock(return_value=mock_resp)

    with patch.object(scf_main.httpx, "Client", return_value=mock_client):
        event = {"body": json.dumps({
            "secret": "test-secret-123",
            "method": "POST",
            "path": "/cgi-bin/material/add_material",
            "params": {"access_token": "tok", "type": "image"},
            "body_type": "multipart",
            "file_name": "01.png",
            "file_field": "media",
            "file_content_base64": file_b64,
        })}
        result = scf_main.main_handler(event, None)

    assert result["statusCode"] == 200
    assert result["body"]["body"]["media_id"] == "abc"


def test_main_handler_forward_failure(scf_main) -> None:
    """转发失败时返回 502 错误"""
    with patch.object(scf_main.httpx, "Client", side_effect=Exception("network error")):
        event = {"body": json.dumps({
            "secret": "test-secret-123",
            "method": "POST",
            "path": "/cgi-bin/test",
            "body_type": "json",
        })}
        result = scf_main.main_handler(event, None)
    assert result["statusCode"] == 502
    assert "转发失败" in result["body"]["error"]


# ===== _error_response 测试 =====


def test_error_response_format(scf_main) -> None:
    """错误响应格式正确"""
    resp = scf_main._error_response(404, "not found")
    assert resp["statusCode"] == 404
    assert resp["headers"]["Content-Type"] == "application/json"
    assert resp["body"]["status_code"] == 404
    assert resp["body"]["error"] == "not found"
    assert resp["body"]["body"] is None


# ===== _parse_response_body 测试 =====


def test_parse_response_body_json(scf_main) -> None:
    """响应体为 JSON 时解析为字典"""
    resp = SimpleNamespace(
        json=lambda: {"ok": True}, text='{"ok":true}'
    )
    assert scf_main._parse_response_body(resp) == {"ok": True}


def test_parse_response_body_text(scf_main) -> None:
    """响应体非 JSON 时返回文本"""
    resp = SimpleNamespace(
        json=MagicMock(side_effect=ValueError("not json")),
        text="plain text",
    )
    assert scf_main._parse_response_body(resp) == "plain text"
