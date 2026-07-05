"""aap export <md> 命令

将 Markdown 文章导出为微信可粘贴的 HTML 与图片包。
对应需求 FR-11(手动导出路径)。
"""
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="导出文章为微信可粘贴的 HTML")


@app.callback(invoke_without_command=True)
def export(
    ctx: typer.Context,
    md_path: Path = typer.Argument(..., help="Markdown 文件路径"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="指定模板名(覆盖 Front Matter)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="输出目录(默认 ./.aap/output)"
    ),
    no_zip: bool = typer.Option(
        False, "--no-zip", help="不打包为 ZIP(只保留目录)"
    ),
    no_clip: bool = typer.Option(
        False, "--no-clip", help="不自动复制 HTML 到剪贴板"
    ),
) -> None:
    """导出文章为微信可粘贴的 HTML

    生成内容:
    - article.html:    内联样式的 HTML,可直接复制到微信编辑器
    - images/01.png:   重命名后的图片(若文章有图片)
    - manifest.json:   图片清单(记录占位符、原路径、待填 media_id)
    - INSTRUCTIONS.txt: 操作指引
    - <name>.zip:      打包文件(便于传输,可用 --no-zip 关闭)

    HTML 也会自动复制到剪贴板(可用 --no-clip 关闭)。
    """
    if ctx.invoked_subcommand is not None:
        return

    if not md_path.exists():
        typer.echo(f"错误: 文件不存在: {md_path}", err=True)
        raise typer.Exit(1)

    from aap.publish.exporter import Exporter

    exporter = Exporter()
    try:
        result = exporter.export(
            md_path,
            cli_template=template,
            output_dir=output,
            zip_output=not no_zip,
            copy_clipboard=not no_clip,
        )
    except FileNotFoundError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"导出失败: {e}", err=True)
        raise typer.Exit(2)

    # 输出结果摘要
    typer.echo("导出完成")
    typer.echo(f"  输出目录: {result.output_dir}")
    typer.echo(f"  HTML:    {result.html_path}")
    if result.manifest_path:
        typer.echo(f"  清单:    {result.manifest_path}")
    typer.echo(f"  指引:    {result.instructions_path}")
    if result.images_zip_path:
        typer.echo(f"  ZIP:     {result.images_zip_path}")
    typer.echo(f"  图片数:  {result.image_count}")

    if not no_clip:
        typer.echo("")
        typer.echo("HTML 已复制到剪贴板,可直接粘贴到微信公众号编辑器")

    if result.image_count > 0:
        typer.echo("")
        typer.echo("下一步:")
        typer.echo(f"  1. 上传 images/ 目录的图片到微信素材库")
        typer.echo(f"  2. 用微信图片 URL 替换 HTML 中的 {{IMG_01}} 等占位符")
        typer.echo(f"  3. 详见 {result.instructions_path}")
