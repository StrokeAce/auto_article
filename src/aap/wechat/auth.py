"""微信 access_token 认证管理

负责获取、缓存与刷新 access_token。

access_token 有效期 2 小时,本模块在到期前 5 分钟主动刷新。
缓存文件: ~/.aap/token_cache.json

刷新方式:
- 直连模式: 直接调用 https://api.weixin.qq.com/cgi-bin/token
- SCF 代理模式: 通过 SCFProxy 转发请求
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from aap.core.models import TokenCache
from aap.utils.path import ensure_aap_home, get_token_cache_path

if TYPE_CHECKING:
    from aap.wechat.client import WeChatClient


# 微信 API 基础 URL
WECHAT_API_BASE = "https://api.weixin.qq.com"

# token 提前刷新的余量(秒),避免临界过期
TOKEN_REFRESH_LEEWAY = 5 * 60

# token 有效期(秒,微信默认 7200)
TOKEN_DEFAULT_EXPIRES_IN = 7200


class AuthManager:
    """微信 access_token 管理器

    负责获取、缓存与刷新 access_token,支持本地缓存与过期判断。
    并发请求用锁防止重复获取。
    """

    def __init__(
        self,
        client: Optional["WeChatClient"] = None,
        cache_path: Optional[Path] = None,
        app_id: str = "",
        app_secret: str = "",
    ) -> None:
        """初始化认证管理器

        Args:
            client: 所属的 WeChatClient 实例(用于复用其 HTTP/SCF 转发能力)
            cache_path: token 缓存文件路径,默认 ~/.aap/token_cache.json
            app_id: 微信公众号 AppID
            app_secret: 微信公众号 AppSecret
        """
        self.client = client
        self.cache_path = cache_path or get_token_cache_path()
        self.app_id = app_id
        self.app_secret = app_secret
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """获取有效的 access_token,优先使用缓存

        流程:
        1. 加载本地缓存
        2. 若未过期(留 5 分钟余量),返回缓存
        3. 否则获取新 token 并写回缓存

        Returns:
            有效的 access_token 字符串

        Raises:
            RuntimeError: 获取 token 失败(网络/鉴权/微信错误)
            ValueError: AppID/AppSecret 未配置
        """
        async with self._lock:
            # 1. 检查缓存
            cache = self._load_cache()
            if cache and not self._is_expired(cache):
                return cache.access_token

            # 2. 拉取新 token
            token = await self._fetch_token()
            return token

    def _is_expired(self, cache: TokenCache) -> bool:
        """判断 token 是否已过期(含提前刷新余量)"""
        if not cache.expires_at:
            return True
        # 统一为 naive UTC 比较
        now = datetime.utcnow()
        expires_at = cache.expires_at
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        return now >= (expires_at - timedelta(seconds=TOKEN_REFRESH_LEEWAY))

    async def _fetch_token(self) -> str:
        """调用微信 API 获取新的 access_token

        Raises:
            ValueError: 配置缺失
            RuntimeError: 微信 API 返回错误
        """
        if not self.app_id or not self.app_secret:
            raise ValueError("缺少 app_id 或 app_secret,请先运行 aap config set 配置")

        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }

        # 复用 client 的请求能力(自动走 SCF 或直连)
        # 但 token 接口不需要 access_token 参数,所以这里直接调底层 request
        if self.client is not None:
            data = await self.client.request_raw("GET", "/cgi-bin/token", params=params)
        else:
            data = await self._direct_request("GET", "/cgi-bin/token", params=params)

        if not isinstance(data, dict):
            raise RuntimeError(f"微信 token 接口返回非 JSON: {data!r}")

        if "access_token" not in data:
            errcode = data.get("errcode", "")
            errmsg = data.get("errmsg", "未知错误")
            raise RuntimeError(f"获取 access_token 失败: [{errcode}] {errmsg}")

        token = data["access_token"]
        expires_in = int(data.get("expires_in", TOKEN_DEFAULT_EXPIRES_IN))
        now = datetime.utcnow()
        cache = TokenCache(
            access_token=token,
            expires_at=now + timedelta(seconds=expires_in),
            fetched_at=now,
        )
        self._save_cache(cache)
        return token

    async def _direct_request(
        self, method: str, path: str, params: Optional[dict] = None
    ) -> dict:
        """直连微信 API(不经过 SCF 代理),用于无 client 时获取 token

        Args:
            method: HTTP 方法
            path: API 路径
            params: 查询参数

        Returns:
            响应 JSON 字典
        """
        import httpx

        url = f"{WECHAT_API_BASE}{path}"
        async with httpx.AsyncClient(timeout=30.0) as http:
            if method.upper() == "GET":
                resp = await http.get(url, params=params)
            else:
                resp = await http.request(method, url, params=params)
            resp.raise_for_status()
            return resp.json()

    def _load_cache(self) -> Optional[TokenCache]:
        """从磁盘加载 token 缓存

        Returns:
            TokenCache 对象,无缓存或解析失败时返回 None
        """
        if not self.cache_path.exists():
            return None
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        # 兼容 expires_at 为 ISO 字符串
        expires_at = data.get("expires_at")
        fetched_at = data.get("fetched_at")
        if isinstance(expires_at, str):
            try:
                data["expires_at"] = datetime.fromisoformat(expires_at)
            except ValueError:
                data["expires_at"] = None
        if isinstance(fetched_at, str):
            try:
                data["fetched_at"] = datetime.fromisoformat(fetched_at)
            except ValueError:
                data["fetched_at"] = None

        try:
            return TokenCache(**data)
        except Exception:
            return None

    def _save_cache(self, cache: TokenCache) -> None:
        """保存 token 缓存到磁盘

        Args:
            cache: TokenCache 对象
        """
        try:
            ensure_aap_home()
            data = {
                "access_token": cache.access_token,
                "expires_at": cache.expires_at.isoformat() if cache.expires_at else None,
                "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
            }
            self.cache_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # 限制文件权限(仅当前用户可读写)
            try:
                import os
                import stat

                os.chmod(self.cache_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        except OSError:
            # 缓存写入失败不致命,下次会重新拉取
            pass

    def invalidate(self) -> None:
        """使缓存失效(删除缓存文件)

        用于 access_token 被微信端失效后(如 40001 错误)的强制刷新。
        """
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
        except OSError:
            pass
