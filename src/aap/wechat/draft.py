"""微信草稿箱 API

提供草稿新增等能力。

接口:
- POST /cgi-bin/draft/add       新增草稿
- POST /cgi-bin/draft/get       获取草稿
- POST /cgi-bin/draft/delete    删除草稿
- POST /cgi-bin/draft/count     草稿总数
"""
from __future__ import annotations

from typing import Any, Optional

from aap.wechat.client import WeChatClient


class DraftAPI:
    """微信草稿箱 API

    提供草稿新增、获取、删除等能力。
    """

    def __init__(self, client: WeChatClient) -> None:
        """初始化草稿 API

        Args:
            client: 微信 API 客户端
        """
        self.client = client

    async def add_draft(self, article_data: dict) -> str:
        """新增草稿到微信公众号

        接口: POST /cgi-bin/draft/add

        Args:
            article_data: 文章数据,字段包括:
                - title:        标题(必填)
                - author:       作者
                - digest:       摘要
                - content:      正文 HTML
                - thumb_media_id: 封面图 media_id(必填)
                - content_source_url: 原文链接
                - need_open_comment: 是否开启留言(0/1)
                - only_fans_can_comment: 仅粉丝可留言(0/1)
                注:以上字段需放在 {"articles": [{...}]} 内

        Returns:
            草稿 media_id

        Raises:
            ValueError: 必填字段缺失
            RuntimeError: 微信 API 返回错误
        """
        # 校验必填字段
        title = article_data.get("title", "")
        content = article_data.get("content", "")
        thumb_media_id = article_data.get("thumb_media_id", "")
        if not title:
            raise ValueError("草稿标题(title)不能为空")
        if not content:
            raise ValueError("草稿正文(content)不能为空")
        if not thumb_media_id:
            raise ValueError("封面图 media_id(thumb_media_id)不能为空")

        # 微信接口要求 articles 数组
        body = {"articles": [article_data]}
        data = await self.client.request(
            method="POST",
            path="/cgi-bin/draft/add",
            json_body=body,
        )
        self._check_error(data, "新增草稿失败")

        media_id = data.get("media_id")
        if not media_id:
            raise RuntimeError(f"微信未返回草稿 media_id: {data}")
        return str(media_id)

    async def get_draft(self, media_id: str) -> dict:
        """获取草稿内容

        接口: POST /cgi-bin/draft/get

        Args:
            media_id: 草稿 media_id

        Returns:
            草稿内容字典
        """
        data = await self.client.request(
            method="POST",
            path="/cgi-bin/draft/get",
            json_body={"media_id": media_id},
        )
        self._check_error(data, "获取草稿失败")
        return data

    async def delete_draft(self, media_id: str) -> bool:
        """删除草稿

        接口: POST /cgi-bin/draft/delete

        Args:
            media_id: 草稿 media_id

        Returns:
            是否删除成功
        """
        data = await self.client.request(
            method="POST",
            path="/cgi-bin/draft/delete",
            json_body={"media_id": media_id},
        )
        # 删除成功时 errcode 为 0
        return bool(data.get("errcode", 0) == 0)

    async def count_drafts(self) -> int:
        """获取草稿总数

        接口: POST /cgi-bin/draft/count

        Returns:
            草稿总数
        """
        data = await self.client.request(
            method="POST",
            path="/cgi-bin/draft/count",
        )
        self._check_error(data, "获取草稿总数失败")
        return int(data.get("total_count", 0))

    @staticmethod
    def _check_error(data: Any, context: str) -> None:
        """检查微信响应是否包含错误,有则抛异常"""
        if not isinstance(data, dict):
            return
        errcode = data.get("errcode", 0)
        if errcode:
            errmsg = data.get("errmsg", "")
            raise RuntimeError(f"{context}: [{errcode}] {errmsg}")
