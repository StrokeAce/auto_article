"""history CLI 命令测试"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from aap.cli.history import app

runner = CliRunner()


def test_history_help() -> None:
    """--help 正常运行"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "list" in result.output or "show" in result.output or "clear" in result.output


def test_history_list_empty(tmp_path: Path) -> None:
    """历史记录文件不存在时 list 返回空提示"""
    history_file = tmp_path / "history.jsonl"
    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "暂无" in result.output


def test_history_list_with_records(tmp_path: Path) -> None:
    """list 显示历史记录(倒序,最新在前)"""
    history_file = tmp_path / "history.jsonl"
    records = [
        {
            "publish_time": "2026-07-05T10:00:00",
            "title": "测试文章一",
            "draft_media_id": "media-001",
            "article_path": "/tmp/a.md",
        },
        {
            "publish_time": "2026-07-05T11:00:00",
            "title": "测试文章二",
            "draft_media_id": "media-002",
            "article_path": "/tmp/b.md",
        },
    ]
    with history_file.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    # 倒序显示,最新的在前
    assert "测试文章二" in result.output
    assert "测试文章一" in result.output


def test_history_show(tmp_path: Path) -> None:
    """show 显示指定记录详情"""
    history_file = tmp_path / "history.jsonl"
    record = {
        "publish_time": "2026-07-05T10:00:00",
        "title": "详情测试",
        "draft_media_id": "media-xyz",
        "article_path": "/tmp/x.md",
        "image_count": 3,
        "template": "minimal",
    }
    history_file.write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["show", "1"])

    assert result.exit_code == 0
    assert "详情测试" in result.output
    assert "media-xyz" in result.output


def test_history_show_not_found(tmp_path: Path) -> None:
    """show 不存在的索引返回错误"""
    history_file = tmp_path / "history.jsonl"
    history_file.write_text(
        json.dumps({"title": "x"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["show", "99"])
    assert result.exit_code != 0
    assert "超出范围" in result.output


def test_history_show_empty_history(tmp_path: Path) -> None:
    """show 在无历史记录时退出码 1"""
    history_file = tmp_path / "history.jsonl"
    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["show", "1"])
    assert result.exit_code != 0


def test_history_clear(tmp_path: Path) -> None:
    """clear --force 清空历史记录"""
    history_file = tmp_path / "history.jsonl"
    history_file.write_text(
        json.dumps({"title": "x"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert history_file.exists()

    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["clear", "--force"])

    assert result.exit_code == 0
    assert not history_file.exists()


def test_history_clear_nonexistent(tmp_path: Path) -> None:
    """clear 不存在的文件提示无需清空"""
    history_file = tmp_path / "history.jsonl"
    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["clear", "--force"])
    assert result.exit_code == 0
    assert "不存在" in result.output


def test_history_path(tmp_path: Path) -> None:
    """path 命令显示历史文件路径"""
    history_file = tmp_path / "history.jsonl"
    with patch("aap.cli.history._resolve_history_path", return_value=history_file):
        result = runner.invoke(app, ["path"])
    assert result.exit_code == 0
    assert str(history_file) in result.output
