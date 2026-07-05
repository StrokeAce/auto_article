"""SCF 云函数入口

部署到腾讯云 SCF 的云函数,转发请求到微信 API,绕开家庭宽带 IP 白名单限制。

工作流程:
1. 接收来自本地 AAP 的 POST 请求(API 网关触发器或直接调用)
2. 验证请求密钥 SCF_SECRET(环境变量)
3. 解析请求载荷: {secret, method, path, params, body, body_type}
4. 用 httpx 转发到微信 API (https://api.weixin.qq.com<path>)
5. 返回响应: {status_code, body, error}

文件上传特殊封装:
    载荷: {secret, method, path, params, body_type="multipart",
           file_name, file_field, file_content_base64}
    SCF 端解码 base64 后以 multipart/form-data 形式转发到微信。

环境变量:
    SCF_SECRET: 访问密钥(必须配置,用于验证请求合法性)
    WECHAT_API_BASE: 微信 API 基础 URL(默认 https://api.weixin.qq.com)

注意: 本文件独立部署,不依赖 aap 包,仅依赖 httpx(SCF Python 运行时预装)。
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

try:
    import httpx
except ImportError:  # SCF 运行时应预装,兜底处理
    httpx = None  # type: ignore

WECHAT_API_BASE = os.environ.get(
    "WECHAT_API_BASE", "https://api.weixin.qq.com"
)
SCF_SECRET = os.environ.get("SCF_SECRET", "")
DEFAULT_TIMEOUT = 60.0


def main_handler(event: dict, context: Any) -> dict:
    """SCF 云函数入口函数

    接收 HTTP 触发器事件,转发请求到微信 API。

    Args:
        event: SCF 事件对象
            - API 网关触发器: 包含 httpMethod/path/body/headers 等
            - 直接调用: 即请求载荷字典 {secret, method, path, ...}
        context: SCF 上下文对象(未使用)

    Returns:
        响应字典:
            - 成功: {"statusCode": 200, "body": <dict>, "error": None}
            - 失败: {"statusCode": <int>, "body": None, "error": <str>}
    """
    try:
        payload = _parse_event(event)
    except ValueError as e:
        return _error_response(400, f"请求格式错误: {e}")

    # 验证密钥
    if not SCF_SECRET:
        return _error_response(500, "SCF_SECRET 环境变量未配置")
    if payload.get("secret") != SCF_SECRET:
        return _error_response(403, "密钥验证失败")

    method = str(payload.get("method", "POST")).upper()
    path = payload.get("path", "")
    params = payload.get("params") or {}
    body_type = str(payload.get("body_type", "json")).lower()

    if not path:
        return _error_response(400, "缺少 path 参数")

    if not path.startswith("/"):
        path = "/" + path

    if httpx is None:
        return _error_response(500, "httpx 未安装")

    # 特殊路径:返回 SCF 出口 IP(供 SCFDeployer.get_egress_ip 调用)
    if path == "/egress-ip":
        ip = get_egress_ip()
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {
                "status_code": 200,
                "body": {"ip": ip},
                "error": None,
            },
        }

    try:
        if body_type == "multipart":
            status_code, resp_body = _forward_multipart(
                method, path, params, payload
            )
        else:
            status_code, resp_body = _forward_json(method, path, params, payload)

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {
                "status_code": status_code,
                "body": resp_body,
                "error": None,
            },
        }
    except Exception as e:
        return _error_response(502, f"转发失败: {e}")


# ===== 内部工具 =====


def _parse_event(event: dict) -> dict:
    """从 SCF event 中解析请求载荷

    支持两种格式:
    1. API 网关触发器: event.body 是 JSON 字符串
    2. 直接调用: event 本身就是载荷字典
    """
    if not isinstance(event, dict):
        raise ValueError("event 必须是字典")

    # 优先尝试 API 网关格式
    body = event.get("body")
    if body is not None:
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            is_b64 = event.get("isBase64Encoded", False)
            if is_b64:
                try:
                    body = base64.b64decode(body).decode("utf-8")
                except Exception as e:
                    raise ValueError(f"base64 解码失败: {e}") from e
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                raise ValueError(f"body 不是合法 JSON: {e}") from e
            if isinstance(data, dict):
                return data
            raise ValueError("body 解析后非字典")

    # 直接调用格式:event 本身是载荷
    if "method" in event or "path" in event or "secret" in event:
        return event

    raise ValueError("无法识别的事件格式")


def _forward_json(
    method: str, path: str, params: dict, payload: dict
) -> tuple[int, Any]:
    """转发 JSON 请求到微信 API"""
    url = WECHAT_API_BASE + path
    body = payload.get("body")

    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        if method == "GET":
            resp = client.get(url, params=params)
        elif method == "POST":
            resp = client.post(url, params=params, json=body)
        else:
            resp = client.request(method, url, params=params, json=body)

    return resp.status_code, _parse_response_body(resp)


def _forward_multipart(
    method: str, path: str, params: dict, payload: dict
) -> tuple[int, Any]:
    """转发 multipart 文件上传请求到微信 API"""
    url = WECHAT_API_BASE + path

    file_name = payload.get("file_name", "file.bin")
    file_field = payload.get("file_field", "media")
    file_b64 = payload.get("file_content_base64", "")

    if not file_b64:
        raise ValueError("file_content_base64 为空")

    try:
        file_bytes = base64.b64decode(file_b64)
    except Exception as e:
        raise ValueError(f"文件 base64 解码失败: {e}") from e

    # 微信素材 API 用 multipart/form-data
    files = {file_field: (file_name, file_bytes, "application/octet-stream")}
    # form 字段拼接在 query 参数中(如 access_token、type)
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.post(url, params=params, files=files)

    return resp.status_code, _parse_response_body(resp)


def _parse_response_body(resp: Any) -> Any:
    """解析微信 API 响应体,优先 JSON,失败则返回文本"""
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError):
        return resp.text


def _error_response(status_code: int, message: str) -> dict:
    """构造错误响应"""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": {
            "status_code": status_code,
            "body": None,
            "error": message,
        },
    }


# ===== 工具函数(供 SCFDeployer 调用获取出口 IP) =====


def get_egress_ip() -> str:
    """获取当前 SCF 函数的出口 IP

    通过访问公共 IP 查询服务获取。

    Returns:
        出口 IP 地址字符串
    """
    if httpx is None:
        return ""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get("https://ifconfig.me/ip")
            if resp.status_code == 200:
                return resp.text.strip()
    except Exception:
        pass
    return ""
