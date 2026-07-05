"""SCF 代理转发客户端

通过腾讯云 SCF 云函数 URL 转发请求到微信 API,绕开家庭宽带 IP 变动导致的 IP 白名单问题。

请求格式(本地 AAP → SCF):
    {
        "secret": "SCF_ACCESS_SECRET",
        "method": "POST",
        "path": "/cgi-bin/draft/add",
        "params": {"access_token": "xxx"},
        "body": {...},            # JSON 请求体
        "body_type": "json"        # json 或 multipart
    }

文件上传特殊封装:
    {
        "secret": "...",
        "method": "POST",
        "path": "/cgi-bin/material/add_material",
        "params": {"access_token": "xxx", "type": "image"},
        "body_type": "multipart",
        "file_name": "01.png",
        "file_content_base64": "..."
    }

响应格式(SCF → 本地 AAP):
    {"status_code": 200, "body": {...}, "error": null}
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

import httpx


class SCFProxy:
    """SCF 代理转发客户端

    通过 SCF 云函数 URL 转发请求到微信 API,绕开 IP 白名单限制。
    """

    def __init__(
        self,
        scf_url: str,
        secret: str = "",
        timeout: float = 60.0,
    ) -> None:
        """初始化 SCF 代理

        Args:
            scf_url: SCF 云函数触发 URL
            secret: 访问密钥(用于验证请求合法性)
            timeout: 请求超时秒数(上传图片可能较慢,默认 60s)
        """
        self.scf_url = scf_url
        self.secret = secret
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "SCFProxy":
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """确保 httpx 客户端已创建"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        """关闭底层 HTTP 客户端"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        body_type: str = "json",
    ) -> dict:
        """通过 SCF 转发请求到微信 API

        Args:
            method: HTTP 方法(GET/POST)
            path: 微信 API 路径,如 /cgi-bin/draft/add
            params: 查询参数(如 access_token)
            body: 请求体(JSON 模式下为字典)
            body_type: 请求体类型,json 或 multipart

        Returns:
            微信 API 响应的 JSON 字典

        Raises:
            RuntimeError: SCF 返回错误或响应异常
        """
        payload: dict[str, Any] = {
            "secret": self.secret,
            "method": method.upper(),
            "path": path,
            "params": params or {},
            "body_type": body_type,
        }
        if body is not None:
            payload["body"] = body

        client = await self._ensure_client()
        try:
            resp = await client.post(self.scf_url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"SCF 请求失败: {e}") from e

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError(f"SCF 返回非 JSON: {resp.text[:200]}") from e

        if not isinstance(data, dict):
            raise RuntimeError(f"SCF 返回格式异常: {data!r}")

        if data.get("error"):
            raise RuntimeError(f"SCF 转发错误: {data['error']}")

        # body 字段可能是 dict 或字符串
        body_data = data.get("body")
        if isinstance(body_data, str):
            # 尝试解析为 JSON
            import json

            try:
                body_data = json.loads(body_data)
            except json.JSONDecodeError:
                pass
        return body_data if isinstance(body_data, dict) else {"data": body_data}

    async def upload_file(
        self,
        path: str,
        params: Optional[dict],
        file_path: Path,
        file_field: str = "media",
    ) -> dict:
        """通过 SCF 上传文件(如图片素材)

        将文件 base64 编码后封装为 multipart 请求体,SCF 端解码后转发。

        Args:
            path: 微信 API 路径,如 /cgi-bin/material/add_material
            params: 查询参数(如 access_token、type=image)
            file_path: 本地文件路径
            file_field: 文件字段名(微信素材 API 用 media)

        Returns:
            微信 API 响应的 JSON 字典

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: 上传失败
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 读取并 base64 编码
        file_bytes = file_path.read_bytes()
        file_b64 = base64.b64encode(file_bytes).decode("ascii")

        payload = {
            "secret": self.secret,
            "method": "POST",
            "path": path,
            "params": params or {},
            "body_type": "multipart",
            "file_name": file_path.name,
            "file_field": file_field,
            "file_content_base64": file_b64,
        }

        client = await self._ensure_client()
        try:
            resp = await client.post(self.scf_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"SCF 文件上传请求失败: {e}") from e

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError(f"SCF 返回非 JSON: {resp.text[:200]}") from e

        if data.get("error"):
            raise RuntimeError(f"SCF 文件上传错误: {data['error']}")

        body_data = data.get("body")
        if isinstance(body_data, str):
            import json

            try:
                body_data = json.loads(body_data)
            except json.JSONDecodeError:
                pass
        return body_data if isinstance(body_data, dict) else {"data": body_data}
