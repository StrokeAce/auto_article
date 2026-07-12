"""aap preview <md_or_dir> 命令

本地预览文章渲染效果,支持微信/HTML/截图三种模式。

两种用法:
1. 指定单个 md 文件: aap preview article.md
2. 指定目录:        aap preview tests/fixtures  (扫描目录下所有 md,首页列出文章列表)
"""
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="本地预览文章渲染效果")


@app.callback(invoke_without_command=True)
def preview(
    ctx: typer.Context,
    md_path: Path = typer.Argument(..., help="Markdown 文件路径或目录(目录模式扫描所有 md)"),
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

    参数 md_path 可以是:
    - 单个 .md 文件:仅预览该文章
    - 目录:扫描目录下所有 .md 文件,首页列出文章列表,点击查看任意一篇
    """
    if ctx.invoked_subcommand is not None:
        return

    if not md_path.exists():
        typer.echo(f"错误: 路径不存在: {md_path}", err=True)
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
    if md_path.is_dir():
        md_files = list(md_path.rglob("*.md"))
        typer.echo(f"目录模式: {md_path}  共 {len(md_files)} 篇 md 文章  模式: {mode}  模板: {template or '(自动)'}")
    else:
        typer.echo(f"文件: {md_path}  模式: {mode}  模板: {template or '(自动)'}")
    typer.echo("按 Ctrl+C 退出")
    server.start()
