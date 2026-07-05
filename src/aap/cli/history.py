"""aap history list/show 命令

查看发布历史。

历史记录存储在 ~/.aap/history.jsonl(每行一条 JSON)。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="查看发布历史")


def _load_history(history_path: Path) -> list[dict]:
    """读取历史文件,返回记录列表(倒序:最新在前)"""
    if not history_path.exists():
        return []
    records: list[dict] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    # 倒序(最新在前)
    records.reverse()
    return records


def _resolve_history_path() -> Path:
    """从配置解析历史文件路径"""
    from aap.config.manager import ConfigManager

    try:
        config = ConfigManager().load()
    except ValueError:
        # 配置文件异常时回退到默认路径
        from aap.utils.path import get_history_path
        return get_history_path()
    from aap.utils.path import get_history_path
    return get_history_path(config.history.file or None)


@app.command("list")
def list_history(
    limit: int = typer.Option(
        20, "--limit", "-n", help="最多显示的记录数(默认 20)"
    ),
) -> None:
    """列出发布历史(最新在前)"""
    history_path = _resolve_history_path()
    records = _load_history(history_path)

    if not records:
        typer.echo("暂无历史记录")
        typer.echo(f"(历史文件: {history_path})")
        return

    typer.echo(f"发布历史(共 {len(records)} 条,显示前 {min(limit, len(records))} 条)")
    typer.echo(f"文件: {history_path}")
    typer.echo("-" * 80)

    for i, rec in enumerate(records[:limit], start=1):
        publish_time = rec.get("publish_time", "?")
        title = rec.get("title", "(无标题)")
        draft_id = rec.get("draft_media_id", "")
        image_count = rec.get("image_count", 0)
        scf_used = "是" if rec.get("scf_used") else "否"

        # 截断过长的 media_id 便于展示
        draft_id_short = draft_id[:16] + "..." if len(draft_id) > 19 else draft_id

        typer.echo(
            f"  #{i:03d}  [{publish_time}]  {title}\n"
            f"        草稿: {draft_id_short}  图片: {image_count}  SCF: {scf_used}"
        )

    typer.echo("-" * 80)
    typer.echo(f"提示: 使用 aap history show <序号> 查看详情")


@app.command("show")
def show(
    index: int = typer.Argument(..., help="历史记录序号(从 aap history list 查看)"),
) -> None:
    """查看指定历史记录详情"""
    history_path = _resolve_history_path()
    records = _load_history(history_path)

    if not records:
        typer.echo("暂无历史记录")
        raise typer.Exit(1)

    if index < 1 or index > len(records):
        typer.echo(f"错误: 序号超出范围(1-{len(records)})", err=True)
        raise typer.Exit(1)

    rec = records[index - 1]
    typer.echo("=" * 60)
    typer.echo(f"历史记录 #{index}")
    typer.echo("=" * 60)
    typer.echo(f"  发布时间:    {rec.get('publish_time', '?')}")
    typer.echo(f"  文章路径:    {rec.get('article_path', '?')}")
    typer.echo(f"  标题:        {rec.get('title', '?')}")
    typer.echo(f"  草稿 media_id: {rec.get('draft_media_id', '?')}")
    typer.echo(f"  封面 media_id: {rec.get('thumb_media_id', '?')}")
    typer.echo(f"  图片数量:    {rec.get('image_count', 0)}")
    typer.echo(f"  使用模板:    {rec.get('template', '?')}")
    typer.echo(f"  是否走 SCF:  {'是' if rec.get('scf_used') else '否'}")


@app.command("clear")
def clear(
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认直接清空"),
) -> None:
    """清空发布历史(删除 history.jsonl)"""
    history_path = _resolve_history_path()
    if not history_path.exists():
        typer.echo("历史文件不存在,无需清空")
        return

    if not force:
        confirm = typer.confirm(f"确认清空发布历史? ({history_path})", default=False)
        if not confirm:
            typer.echo("已取消")
            raise typer.Exit(0)

    history_path.unlink()
    typer.echo(f"已清空历史记录: {history_path}")


@app.command("path")
def path() -> None:
    """显示历史文件路径"""
    history_path = _resolve_history_path()
    typer.echo(str(history_path))
    typer.echo(f"存在: {'是' if history_path.exists() else '否'}")
