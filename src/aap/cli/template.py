"""aap template list/edit 命令组

管理样式模板。
"""
import typer

app = typer.Typer(help="管理样式模板")


@app.command("list")
def list_templates() -> None:
    """列出所有可用模板"""
    from aap.templates.manager import TemplateManager

    manager = TemplateManager()
    templates = manager.list_templates()
    for name in templates:
        typer.echo(name)


@app.command("edit")
def edit(
    name: str = typer.Argument(
        None, help="待编辑的模板名称(省略则使用默认模板)"
    ),
    port: int = typer.Option(7000, "--port", "-p", help="编辑器监听端口"),
    sample: str = typer.Option(
        None, "--sample", help="示例文章路径,用于实时预览"
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="不自动打开浏览器"
    ),
) -> None:
    """启动可视化模板编辑器

    打开浏览器编辑指定模板的 CSS 与 YAML 配置,右侧实时预览渲染效果。
    保存时会写入用户全局模板目录(~/.aap/templates/<name>/)。
    """
    from pathlib import Path

    from aap.templates.editor.server import EditorServer

    server = EditorServer(
        port=port,
        sample_article=Path(sample) if sample else None,
        template_name=name,
        open_browser=not no_browser,
    )
    server.start()
