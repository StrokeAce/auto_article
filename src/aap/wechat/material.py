"""微信素材管理 API

提供图片上传等素材管理能力。

接口:
- POST /cgi-bin/material/add_material  上传永久素材(返回 media_id + url)
- POST /cgi-bin/media/uploadimg        上传图文消息内图片(仅返回 url)

注意:
- 正文图片用 uploadimg(只返回 url,可用于 content 中的 img src)
- 封面图用 add_material(返回 media_id,用于 thumb_media_id)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aap.wechat.client import WeChatClient


class MaterialAPI:
    """微信素材管理 API

    提供图片上传等素材管理能力。
    """

    def __init__(self, client: WeChatClient) -> None:
        """初始化素材 API

        Args:
            client: 微信 API 客户端
        """
        self.client = client

    async def upload_image(self, image_path: Path) -> dict:
        """上传图片到素材库(永久素材)

        接口: POST /cgi-bin/material/add_material
        参数: type=image, multipart 文件

        Args:
            image_path: 本地图片文件路径

        Returns:
            包含 media_id 与 url 的字典,例如:
            {"media_id": "abc123", "url": "https://mmbiz.qpic.cn/..."}

        Raises:
            FileNotFoundError: 图片文件不存在
            RuntimeError: 微信 API 返回错误
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        data = await self.client.upload_file(
            path="/cgi-bin/material/add_material",
            params={"type": "image"},
            file_path=image_path,
            file_field="media",
        )
        self._check_error(data, f"上传素材失败: {image_path.name}")
        return data

    async def upload_content_image(self, image_path: Path) -> str:
        """上传图文消息内的图片(只返回 url,无 media_id)

        接口: POST /cgi-bin/media/uploadimg
        用于正文中的 <img src="...">,微信要求图片必须在 mmbiz.qpic.cn 域下。

        Args:
            image_path: 本地图片文件路径

        Returns:
            微信图片 URL(以 https://mmbiz.qpic.cn/ 开头)

        Raises:
            FileNotFoundError: 图片文件不存在
            RuntimeError: 微信 API 返回错误
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        data = await self.client.upload_file(
            path="/cgi-bin/media/uploadimg",
            params=None,
            file_path=image_path,
            file_field="media",
        )
        self._check_error(data, f"上传正文图片失败: {image_path.name}")

        url = data.get("url")
        if not url:
            raise RuntimeError(f"微信未返回图片 URL: {data}")
        return str(url)

    async def upload_thumb(self, image_path: Path) -> str:
        """上传封面图(作为图文消息的 thumb_media_id)

        复用 add_material 接口,返回 media_id。

        Args:
            image_path: 本地封面图路径

        Returns:
            封面图的 media_id
        """
        data = await self.upload_image(image_path)
        media_id = data.get("media_id")
        if not media_id:
            raise RuntimeError(f"微信未返回封面 media_id: {data}")
        return str(media_id)

    @staticmethod
    def _check_error(data: Any, context: str) -> None:
        """检查微信响应是否包含错误,有则抛异常"""
        if not isinstance(data, dict):
            return
        errcode = data.get("errcode", 0)
        if errcode:
            errmsg = data.get("errmsg", "")
            raise RuntimeError(f"{context}: [{errcode}] {errmsg}")
