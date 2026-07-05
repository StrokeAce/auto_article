"""aap publish <md> 命令

将 Markdown 文章发布到微信公众号草稿箱。
"""
import asyncio
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="发布文章到微信公众号草稿箱")


@app.callback(invoke_without_command=True)
def publish(
    ctx: typer.Context,
    md_path: Path = typer.Argument(..., help="Markdown 文件路径"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="指定模板名(覆盖 Front Matter)"
    ),
) -> None:
    """将 Markdown 文章发布到微信公众号草稿箱

    完整流程:
    1. 解析 Markdown 与 Front Matter
    2. 应用模板渲染为微信兼容 HTML
    3. 上传正文图片到微信素材库
    4. 上传封面图到微信素材库
    5. 调用草稿箱 API 上传文章
    6. 记录发布历史

    发布成功后,需要登录微信公众号后台手动点击"发布"。
    """
    if ctx.invoked_subcommand is not None:
        return

    if not md_path.exists():
        typer.echo(f"错误: 文件不存在: {md_path}", err=True)
        raise typer.Exit(1)

    from aap.publish.publisher import Publisher

    async def _run() -> None:
        publisher = Publisher()
        try:
            result = await publisher.publish(md_path, cli_template=template)
        except FileNotFoundError as e:
            typer.echo(f"错误: {e}", err=True)
            raise typer.Exit(1)
        except ValueError as e:
            typer.echo(f"配置错误: {e}", err=True)
            typer.echo("提示: 请先运行 aap config init 初始化配置", err=True)
            raise typer.Exit(2)
        except RuntimeError as e:
            typer.echo(f"发布失败: {e}", err=True)
            raise typer.Exit(3)

        if not result.success:
            typer.echo(f"发布失败: {result.error}", err=True)
            raise typer.Exit(4)

        # 成功输出
        typer.echo("")
        typer.echo("文章已上传到草稿箱")
        typer.echo("")
        typer.echo(f"  标题:           {result.article_title}")
        typer.echo(f"  草稿 media_id:  {result.draft_media_id}")
        typer.echo(f"  封面 media_id:  {result.thumb_media_id}")
        typer.echo(f"  图片数量:       {result.image_count} 张(已上传到素材库)")
        typer.echo("")
        typer.echo("下一步:")
        typer.echo("  1. 登录 https://mp.weixin.qq.com")
        typer.echo("  2. 进入 草稿箱")
        typer.echo("  3. 找到本文草稿,点击预览")
        typer.echo("  4. 确认排版无误后,点击 发布")

    asyncio.run(_run())
