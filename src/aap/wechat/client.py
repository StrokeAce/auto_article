"""微信公众号 API 统一客户端

封装与微信 API 的交互,自动根据配置选择直连或经 SCF 代理转发。

路由策略:
- scf.enabled == True: 所有请求经 SCF 代理转发
- scf.enabled == False: 直连微信 API

使用方式:
    client = WeChatClient(config)
    await client.material.upload_image(Path("cover.png"))
    await client.draft.add_draft({...})
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import httpx

from aap.core.models import AppConfig
from aap.scf.proxy import SCFProxy
from aap.wechat.auth import AuthManager, WECHAT_API_BASE

# 微信 API 错误码: access_token 失效,需要重新获取
ERRCODE_INVALID_TOKEN = {40001, 42001, 40014}


class WeChatClient:
    """微信公众号 API 统一客户端

    封装与微信 API 的交互,支持直连或经 SCF 代理转发。
    """

    def __init__(self, config: AppConfig) -> None:
        """初始化客户端

        Args:
            config: 应用配置(包含 account/scf 等)
        """
        self.config = config
        self.use_scf = config.scf.enabled and bool(config.scf.url)

        # 鉴权管理器
        self.auth = AuthManager(
            client=self,
            app_id=config.account.app_id,
            app_secret=config.account.app_secret,
        )

        # HTTP 客户端(直连模式用)
        self._http: Optional[httpx.AsyncClient] = None

        # SCF 代理客户端(SCF 模式用)
        self._scf: Optional[SCFProxy] = None
        if self.use_scf:
            self._scf = SCFProxy(
                scf_url=config.scf.url,
                secret=config.scf.secret,
            )

        # 子 API(懒加载)
        from aap.wechat.material import MaterialAPI
        from aap.wechat.draft import DraftAPI

        self.material = MaterialAPI(self)
        self.draft = DraftAPI(self)

    async def __aenter__(self) -> "WeChatClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """关闭底层连接"""
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        if self._scf is not None:
            await self._scf.aclose()

    async def get_token(self) -> str:
        """获取当前有效的 access_token"""
        return await self.auth.get_token()

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        retry_on_token_error: bool = True,
    ) -> dict:
        """发送已鉴权请求到微信 API,自动附加 access_token

        Args:
            method: HTTP 方法(GET/POST)
            path: API 路径,如 /cgi-bin/draft/add
            params: 额外查询参数(access_token 会自动附加)
            json_body: JSON 请求体
            retry_on_token_error: 遇到 token 失效错误时是否重试(默认 True)

        Returns:
            微信 API 响应 JSON 字典

        Raises:
            RuntimeError: 请求失败或微信返回错误
        """
        # 获取 access_token 并合并到 params
        token = await self.get_token()
        merged_params = dict(params or {})
        merged_params["access_token"] = token

        data = await self.request_raw(method, path, params=merged_params, json_body=json_body)

        # 检查 token 失效错误,自动刷新并重试一次
        if (
            retry_on_token_error
            and isinstance(data, dict)
            and data.get("errcode") in ERRCODE_INVALID_TOKEN
        ):
            self.auth.invalidate()
            return await self.request(
                method, path, params=params, json_body=json_body, retry_on_token_error=False
            )

        return data

    async def request_raw(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """发送原始请求(不自动附加 access_token)到微信 API

        用于获取 token 接口本身,或需要手动控制 access_token 的场景。

        Args:
            method: HTTP 方法
            path: API 路径
            params: 查询参数
            json_body: JSON 请求体

        Returns:
            微信 API 响应 JSON 字典
        """
        if self.use_scf and self._scf is not None:
            return await self._scf.request(
                method=method,
                path=path,
                params=params,
                body=json_body,
                body_type="json",
            )
        return await self._direct_request(method, path, params=params, json_body=json_body)

    async def upload_file(
        self,
        path: str,
        params: Optional[dict],
        file_path: Path,
        file_field: str = "media",
    ) -> dict:
        """上传文件到微信 API(自动附加 access_token)

        Args:
            path: API 路径,如 /cgi-bin/material/add_material
            params: 额外查询参数
            file_path: 本地文件路径
            file_field: 文件字段名

        Returns:
            微信 API 响应 JSON 字典
        """
        token = await self.get_token()
        merged_params = dict(params or {})
        merged_params["access_token"] = token

        if self.use_scf and self._scf is not None:
            return await self._scf.upload_file(
                path=path,
                params=merged_params,
                file_path=file_path,
                file_field=file_field,
            )
        return await self._direct_upload(
            path=path, params=merged_params, file_path=file_path, file_field=file_field
        )

    async def _direct_request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """直连微信 API"""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        url = f"{WECHAT_API_BASE}{path}"
        if method.upper() == "GET":
            resp = await self._http.get(url, params=params)
        else:
            resp = await self._http.request(method, url, params=params, json=json_body)
        resp.raise_for_status()
        return resp.json()

    async def _direct_upload(
        self,
        path: str,
        params: Optional[dict],
        file_path: Path,
        file_field: str = "media",
    ) -> dict:
        """直连上传文件"""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=60.0)
        url = f"{WECHAT_API_BASE}{path}"
        with open(file_path, "rb") as f:
            files = {file_field: (file_path.name, f, None)}
            resp = await self._http.post(url, params=params, files=files)
        resp.raise_for_status()
        return resp.json()
