"""aap preview <md> 命令

本地预览文章渲染效果,支持微信/HTML/截图三种模式。
"""
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="本地预览文章渲染效果")


@app.callback(invoke_without_command=True)
def preview(
    ctx: typer.Context,
    md_path: Path = typer.Argument(..., help="Markdown 文件路径"),
    mode: str = typer.Option(
        "wechat", "--mode", "-m", help="预览模式: wechat/html/screenshot"
    ),
    port: int = typer.Option(7788, "--port", "-p", help="预览服务端口"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="指定模板名(覆盖 Front Matter)"
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="不自动打开浏览器"
    ),
) -> None:
    """本地预览文章渲染效果

    启动一个本地 Web 服务,在浏览器中实时预览 Markdown 文章渲染效果。
    支持 wechat 模式(模拟微信编辑器外观)与 html 模式(纯 HTML 调试)。
    修改 Markdown 文件后,页面会自动刷新。
    """
    if ctx.invoked_subcommand is not None:
        return

    if not md_path.exists():
        typer.echo(f"错误: 文件不存在: {md_path}", err=True)
        raise typer.Exit(1)

    from aap.preview.server import PreviewServer

    server = PreviewServer(
        md_path,
        mode=mode,
        port=port,
        open_browser=not no_browser,
        template_name=template,
    )
    typer.echo(f"AAP 预览服务启动中: http://127.0.0.1:{port}")
    typer.echo(f"文件: {md_path}  模式: {mode}  模板: {template or '(自动)'}")
    typer.echo("按 Ctrl+C 退出")
    server.start()
