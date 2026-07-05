"""AAP 主 CLI 入口

使用 Typer 框架,注册所有子命令。
"""
import typer

from aap.cli import (
    config_cli,
    export,
    history,
    image,
    preview,
    publish,
    scf,
    template,
    test_cmd,
)

app = typer.Typer(
    name="aap",
    help="AAP - 微信公众号文章自动化发布工具",
    no_args_is_help=True,
)

# 注册子命令
app.add_typer(publish.app, name="publish", help="发布文章到微信公众号草稿箱")
app.add_typer(export.app, name="export", help="导出文章为微信可粘贴的 HTML")
app.add_typer(preview.app, name="preview", help="本地预览文章渲染效果")
app.add_typer(template.app, name="template", help="管理样式模板")
app.add_typer(config_cli.app, name="config", help="初始化或修改配置")
app.add_typer(scf.app, name="scf", help="管理腾讯云 SCF 代理")
app.add_typer(image.app, name="image", help="图片资源管理")
app.add_typer(history.app, name="history", help="查看发布历史")
app.add_typer(test_cmd.app, name="test", help="兼容性测试工具")


if __name__ == "__main__":
    app()
