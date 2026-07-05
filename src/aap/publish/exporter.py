"""文章导出器

执行手动导出流程(对应需求 FR-11):
1. 解析 Markdown (parser)
2. 解析模板 (template_manager)
3. 渲染 HTML (renderer, 图片用占位符)
4. 打包图片到 images/ 子目录
5. 生成 manifest.json
6. 生成 INSTRUCTIONS.txt
7. (可选)打包整个输出目录为 ZIP
8. (可选)复制 HTML 到剪贴板

输出目录结构:
    <output_dir>/<md_stem>/
    ├── article.html
    ├── images/
    │   └── 01.png
    ├── manifest.json
    ├── INSTRUCTIONS.txt
    └── <md_stem>.zip (可选)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from aap.core.models import ExportResult
from aap.core.parser import ArticleParser
from aap.core.renderer import HTMLRenderer
from aap.image.packer import ImagePacker
from aap.image.scanner import ImageScanner
from aap.templates.manager import TemplateManager
from aap.utils.clipboard import copy_to_clipboard


class Exporter:
    """文章导出器

    执行手动导出流程:
    解析 Markdown → 渲染 HTML → 打包图片 → 生成 HTML 与说明文档。
    """

    def __init__(
        self,
        parser: Optional[ArticleParser] = None,
        renderer: Optional[HTMLRenderer] = None,
        template_manager: Optional[TemplateManager] = None,
        scanner: Optional[ImageScanner] = None,
        packer: Optional[ImagePacker] = None,
    ) -> None:
        self.parser = parser or ArticleParser()
        self.renderer = renderer or HTMLRenderer()
        self.template_manager = template_manager or TemplateManager()
        self.scanner = scanner or ImageScanner()
        self.packer = packer or ImagePacker()

    def export(
        self,
        md_path: Path,
        cli_template: Optional[str] = None,
        output_dir: Optional[Path] = None,
        zip_output: bool = True,
        copy_clipboard: bool = True,
    ) -> ExportResult:
        """导出文章为微信可粘贴的 HTML

        Args:
            md_path: Markdown 文件路径
            cli_template: 命令行指定的模板名(覆盖 Front Matter)
            output_dir: 输出根目录(默认 ./.aap/output 或配置项)
            zip_output: 是否打包输出为 ZIP
            copy_clipboard: 是否复制 HTML 到剪贴板

        Returns:
            导出结果对象
        """
        md_path = Path(md_path).resolve()
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown 文件不存在: {md_path}")

        # 1. 解析文章
        article = self.parser.parse(md_path)

        # 2. 解析模板
        template_name = self.template_manager.resolve_template_name(article, cli_template)
        try:
            template = self.template_manager.load_template(template_name)
            css = self.template_manager.load_template_css(template_name)
        except FileNotFoundError:
            # 回退到 minimal
            template = self.template_manager.load_template("minimal")
            css = self.template_manager.load_template_css("minimal")
            template_name = "minimal"

        # 3. 渲染 HTML(图片用占位符)
        html = self.renderer.render_for_export(article, template, css=css)

        # 4. 准备输出目录
        if output_dir is None:
            output_dir = Path.cwd() / ".aap" / "output"
        output_dir = Path(output_dir)
        # 在 output_dir 下创建以文章名为名的子目录,避免多次导出相互覆盖
        article_output_dir = output_dir / md_path.stem
        # 加时间戳后缀,避免覆盖历史导出
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        article_output_dir = article_output_dir.with_name(f"{md_path.stem}_{timestamp}")
        article_output_dir.mkdir(parents=True, exist_ok=True)

        # 5. 写入 article.html
        html_path = article_output_dir / "article.html"
        html_path.write_text(html, encoding="utf-8")

        # 6. 扫描并打包图片
        images = self.scanner.scan(article)
        existing, missing = self.scanner.check_exists(images)
        if missing:
            # 警告但不中断
            pass

        if existing:
            self.packer.pack(existing, article_output_dir, skip_missing=True)
            # 重新生成 manifest(包含所有图片,缺失的标记)
            manifest = self.packer.generate_manifest(
                images=images,
                article_path=md_path,
                extra={
                    "title": article.meta.title,
                    "template": template_name,
                },
            )
            manifest_path = self.packer.write_manifest(manifest, article_output_dir)
        else:
            manifest_path = None

        # 7. 写 INSTRUCTIONS.txt(即使无图片也生成基础指引)
        instructions_path = self.packer.write_instructions(
            images=images,
            output_dir=article_output_dir,
            article_title=article.meta.title,
        )

        # 8. 可选:打包为 ZIP
        images_zip_path = None
        if zip_output:
            images_zip_path = self.packer.zip_output(article_output_dir)

        # 9. 可选:复制 HTML 到剪贴板
        if copy_clipboard:
            try:
                copy_to_clipboard(html)
            except Exception:
                pass

        return ExportResult(
            success=True,
            output_dir=article_output_dir,
            html_path=html_path,
            images_zip_path=images_zip_path,
            manifest_path=manifest_path,
            instructions_path=instructions_path,
            image_count=len(images),
        )
