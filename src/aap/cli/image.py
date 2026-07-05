"""aap image bind 命令

图片资源管理。
"""
from pathlib import Path

import typer

app = typer.Typer(help="图片资源管理")


@app.command("bind")
def bind(
    manifest: Path = typer.Argument(..., help="图片清单文件路径"),
) -> None:
    """交互式绑定图片 media_id"""
    from aap.image.binder import ImageBinder

    binder = ImageBinder()
    binder.bind(manifest)
