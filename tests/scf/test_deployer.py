"""SCFDeployer 测试

测试纯函数逻辑,不调用真实腾讯云 API。
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aap.scf.deployer import (
    DEFAULT_FUNCTION_NAME,
    DEFAULT_MEMORY,
    DEFAULT_RUNTIME,
    DEFAULT_TIMEOUT,
    FUNCTION_SRC_DIR,
    SCFDeployer,
)


# ===== __init__ 测试 =====


def test_init_defaults() -> None:
    """默认参数初始化"""
    deployer = SCFDeployer()
    assert deployer.region == "ap-shanghai"
    assert deployer.function_name == DEFAULT_FUNCTION_NAME
    assert deployer.scf_url is None
    assert deployer.scf_secret is None


def test_init_custom() -> None:
    """自定义参数初始化"""
    deployer = SCFDeployer(
        region="ap-guangzhou",
        function_name="my-func",
        scf_url="https://example.com",
        scf_secret="secret",
    )
    assert deployer.region == "ap-guangzhou"
    assert deployer.function_name == "my-func"
    assert deployer.scf_url == "https://example.com"
    assert deployer.scf_secret == "secret"


# ===== _pack_function_code 测试 =====


def test_pack_function_code_creates_zip() -> None:
    """打包函数代码生成 ZIP 文件"""
    deployer = SCFDeployer()
    zip_path = deployer._pack_function_code()

    try:
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        # 验证 ZIP 内包含 main.py
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "main.py" in names
            # main.py 应包含 main_handler
            content = zf.read("main.py").decode("utf-8")
            assert "main_handler" in content
    finally:
        # 清理临时文件
        if zip_path.exists():
            zip_path.unlink()
        # 清理临时目录
        try:
            zip_path.parent.rmdir()
        except OSError:
            pass


def test_function_src_dir_exists() -> None:
    """SCF 函数源码目录存在"""
    assert FUNCTION_SRC_DIR.exists()
    assert (FUNCTION_SRC_DIR / "main.py").exists()


# ===== _extract_trigger_url 测试 =====


def test_extract_trigger_url_from_string() -> None:
    """从 JSON 字符串中提取 URL"""
    deployer = SCFDeployer()
    info = json.dumps({"url": "https://service.example.com/release"})
    assert deployer._extract_trigger_url(info) == "https://service.example.com/release"


def test_extract_trigger_url_from_dict() -> None:
    """从字典中提取 URL"""
    deployer = SCFDeployer()
    info = {"URL": "https://api.example.com/invocation"}
    assert deployer._extract_trigger_url(info) == "https://api.example.com/invocation"


def test_extract_trigger_url_service_domain() -> None:
    """从 service.release.domain 字段提取 URL"""
    deployer = SCFDeployer()
    info = {"service": {"release": {"domain": "https://x.example.com"}}}
    assert deployer._extract_trigger_url(info) == "https://x.example.com"


def test_extract_trigger_url_empty() -> None:
    """空信息返回空字符串"""
    deployer = SCFDeployer()
    assert deployer._extract_trigger_url("") == ""
    assert deployer._extract_trigger_url(None) == ""


def test_extract_trigger_url_invalid_json() -> None:
    """非法 JSON 返回空字符串"""
    deployer = SCFDeployer()
    assert deployer._extract_trigger_url("not-json{") == ""


def test_extract_trigger_url_no_url_field() -> None:
    """无 URL 字段返回空字符串"""
    deployer = SCFDeployer()
    assert deployer._extract_trigger_url({"foo": "bar"}) == ""


# ===== _get_client 测试 =====


def test_get_client_missing_credentials() -> None:
    """未提供凭据抛 RuntimeError"""
    deployer = SCFDeployer()
    with pytest.raises(RuntimeError, match="必须提供 secret_id"):
        deployer._get_client("", "")


def test_get_client_sdk_not_installed() -> None:
    """SDK 未安装时抛 RuntimeError 并提示安装命令"""
    deployer = SCFDeployer()
    with patch.dict("sys.modules", {"tencentcloud": None, "tencentcloud.common": None}):
        with pytest.raises(RuntimeError, match="tencentcloud-sdk-python 未安装"):
            deployer._get_client("id", "key")


# ===== get_egress_ip 测试 =====


def test_get_egress_ip_no_url() -> None:
    """未配置 scf_url 时抛 RuntimeError"""
    deployer = SCFDeployer()
    with pytest.raises(RuntimeError, match="未配置 scf_url"):
        deployer.get_egress_ip()


def test_get_egress_ip_success() -> None:
    """成功获取出口 IP"""
    deployer = SCFDeployer(scf_url="https://example.com", scf_secret="s")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "body": {
            "status_code": 200,
            "body": {"ip": "1.2.3.4"},
            "error": None,
        }
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post = MagicMock(return_value=mock_resp)

    with patch("httpx.Client", return_value=mock_client):
        ip = deployer.get_egress_ip()
    assert ip == "1.2.3.4"


def test_get_egress_ip_request_failure() -> None:
    """请求失败抛 RuntimeError"""
    deployer = SCFDeployer(scf_url="https://example.com", scf_secret="s")
    import httpx

    with patch("httpx.Client", side_effect=httpx.HTTPError("timeout")):
        with pytest.raises(RuntimeError, match="请求 SCF 失败"):
            deployer.get_egress_ip()


def test_get_egress_ip_body_as_string() -> None:
    """中间层 body 为字符串时自动 JSON 解析"""
    deployer = SCFDeployer(scf_url="https://example.com", scf_secret="s")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    # SCF 返回的 body 字段为 JSON 字符串
    mock_resp.json.return_value = {
        "statusCode": 200,
        "body": json.dumps({
            "status_code": 200,
            "body": {"ip": "5.6.7.8"},
            "error": None,
        }),
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post = MagicMock(return_value=mock_resp)

    with patch("httpx.Client", return_value=mock_client):
        ip = deployer.get_egress_ip()
    assert ip == "5.6.7.8"


# ===== get_status 测试 =====


def test_get_status_function_not_exists() -> None:
    """函数不存在时返回 exists=False"""
    deployer = SCFDeployer()
    mock_client = MagicMock()

    # 由于 SDK 可能未安装,直接 mock _try_get_function
    with patch.object(deployer, "_try_get_function", return_value=None):
        with patch.object(deployer, "_get_client", return_value=mock_client):
            result = deployer.get_status(secret_id="id", secret_key="key")
    assert result["exists"] is False
    assert result["function_name"] == DEFAULT_FUNCTION_NAME


def test_get_status_function_exists() -> None:
    """函数存在时返回完整状态"""
    deployer = SCFDeployer()
    func_info = {
        "Runtime": DEFAULT_RUNTIME,
        "MemorySize": DEFAULT_MEMORY,
        "Timeout": DEFAULT_TIMEOUT,
        "Status": "Active",
        "ModifyTime": "2026-01-01 00:00:00",
    }
    mock_client = MagicMock()
    with patch.object(deployer, "_try_get_function", return_value=func_info):
        with patch.object(deployer, "_list_triggers", return_value=[{"Type": "apigw", "TriggerName": "t"}]):
            with patch.object(deployer, "_get_client", return_value=mock_client):
                result = deployer.get_status(secret_id="id", secret_key="key")

    assert result["exists"] is True
    assert result["runtime"] == DEFAULT_RUNTIME
    assert result["memory"] == DEFAULT_MEMORY
    assert result["status"] == "Active"
    assert len(result["triggers"]) == 1
