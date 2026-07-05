"""DraftAPI 测试

测试字段校验与错误处理逻辑,通过 mock WeChatClient。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aap.wechat.draft import DraftAPI


@pytest.fixture
def mock_client():
    """Mock WeChatClient"""
    client = MagicMock()
    client.request = AsyncMock()
    return client


@pytest.fixture
def draft_api(mock_client):
    return DraftAPI(client=mock_client)


# ===== add_draft 测试 =====


@pytest.mark.asyncio
async def test_add_draft_missing_title(draft_api) -> None:
    """标题为空抛 ValueError"""
    with pytest.raises(ValueError, match="title"):
        await draft_api.add_draft({
            "title": "",
            "content": "<p>x</p>",
            "thumb_media_id": "media123",
        })


@pytest.mark.asyncio
async def test_add_draft_missing_content(draft_api) -> None:
    """正文为空抛 ValueError"""
    with pytest.raises(ValueError, match="content"):
        await draft_api.add_draft({
            "title": "T",
            "content": "",
            "thumb_media_id": "media123",
        })


@pytest.mark.asyncio
async def test_add_draft_missing_thumb(draft_api) -> None:
    """封面 media_id 为空抛 ValueError"""
    with pytest.raises(ValueError, match="thumb_media_id"):
        await draft_api.add_draft({
            "title": "T",
            "content": "<p>x</p>",
            "thumb_media_id": "",
        })


@pytest.mark.asyncio
async def test_add_draft_success(draft_api, mock_client) -> None:
    """成功新增草稿返回 media_id"""
    mock_client.request.return_value = {"media_id": "draft-001", "errcode": 0}

    article_data = {
        "title": "测试标题",
        "content": "<p>正文</p>",
        "thumb_media_id": "thumb-001",
        "author": "AAP",
    }
    media_id = await draft_api.add_draft(article_data)

    assert media_id == "draft-001"
    # 验证 request 被正确调用
    mock_client.request.assert_called_once()
    call_args = mock_client.request.call_args
    assert call_args.kwargs["method"] == "POST"
    assert call_args.kwargs["path"] == "/cgi-bin/draft/add"
    body = call_args.kwargs["json_body"]
    assert "articles" in body
    assert body["articles"][0]["title"] == "测试标题"


@pytest.mark.asyncio
async def test_add_draft_wechat_error(draft_api, mock_client) -> None:
    """微信返回错误码时抛 RuntimeError"""
    mock_client.request.return_value = {
        "errcode": 40001,
        "errmsg": "invalid credential",
    }
    with pytest.raises(RuntimeError, match="新增草稿失败.*40001"):
        await draft_api.add_draft({
            "title": "T",
            "content": "<p>x</p>",
            "thumb_media_id": "m",
        })


@pytest.mark.asyncio
async def test_add_draft_no_media_id(draft_api, mock_client) -> None:
    """微信未返回 media_id 时抛 RuntimeError"""
    mock_client.request.return_value = {"errcode": 0, "errmsg": "ok"}
    with pytest.raises(RuntimeError, match="未返回草稿 media_id"):
        await draft_api.add_draft({
            "title": "T",
            "content": "<p>x</p>",
            "thumb_media_id": "m",
        })


# ===== get_draft / delete_draft / count_drafts 测试 =====


@pytest.mark.asyncio
async def test_get_draft_success(draft_api, mock_client) -> None:
    """成功获取草稿"""
    mock_client.request.return_value = {
        "news_item": [{"title": "T"}],
        "errcode": 0,
    }
    result = await draft_api.get_draft("media-001")
    assert result["news_item"][0]["title"] == "T"


@pytest.mark.asyncio
async def test_delete_draft_success(draft_api, mock_client) -> None:
    """成功删除草稿"""
    mock_client.request.return_value = {"errcode": 0, "errmsg": "ok"}
    result = await draft_api.delete_draft("media-001")
    assert result is True


@pytest.mark.asyncio
async def test_delete_draft_failure(draft_api, mock_client) -> None:
    """删除失败返回 False"""
    mock_client.request.return_value = {"errcode": 40013, "errmsg": "invalid"}
    result = await draft_api.delete_draft("media-001")
    assert result is False


@pytest.mark.asyncio
async def test_count_drafts_success(draft_api, mock_client) -> None:
    """成功获取草稿总数"""
    mock_client.request.return_value = {"total_count": 8, "errcode": 0}
    count = await draft_api.count_drafts()
    assert count == 8


@pytest.mark.asyncio
async def test_count_drafts_default_zero(draft_api, mock_client) -> None:
    """无 total_count 字段时返回 0"""
    mock_client.request.return_value = {"errcode": 0}
    count = await draft_api.count_drafts()
    assert count == 0


# ===== _check_error 测试 =====


def test_check_error_no_error() -> None:
    """无错误码时不抛异常"""
    DraftAPI._check_error({"errcode": 0, "errmsg": "ok"}, "ctx")


def test_check_error_with_error() -> None:
    """有错误码时抛 RuntimeError"""
    with pytest.raises(RuntimeError, match="ctx.*40001"):
        DraftAPI._check_error({"errcode": 40001, "errmsg": "bad"}, "ctx")


def test_check_error_non_dict() -> None:
    """非字典响应不抛异常"""
    DraftAPI._check_error("not dict", "ctx")
    DraftAPI._check_error(None, "ctx")
