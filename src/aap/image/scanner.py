"""图片扫描器

扫描文章 HTML 中的所有图片引用,生成 ImageRef 列表。

由于 ArticleParser 在解析阶段已经完成图片扫描并填充到 article.images,
本模块主要提供:
1. 独立的 HTML 字符串扫描入口(供外部 HTML 使用)
2. 文件存在性检查与缺失图片报告
3. 与 Article.images 同步的工具方法
"""
from __future__ import annotations

from pathlib import Path

from aap.core.html_utils import extract_images
from aap.core.models import Article, ImageRef


class ImageScanner:
    """图片扫描器

    扫描文章 HTML 中的所有图片引用,生成 ImageRef 列表。
    """

    def scan(self, article: Article) -> list[ImageRef]:
        """从 Article 中扫描图片引用

        优先使用 article.images(parser 已填充),
        若为空则从 article.content_html 重新扫描。

        Args:
            article: 文章对象

        Returns:
            图片引用列表(按出现顺序,已去重)
        """
        # parser 已经在解析时扫描过,直接复用
        if article.images:
            return list(article.images)

        # 兜底:从 HTML 重新扫描
        srcs = extract_images(article.content_html)
        if not srcs:
            return []

        images: list[ImageRef] = []
        seen: set[str] = set()
        base_dir = (
            Path(article.source_path).parent
            if article.source_path
            else Path.cwd()
        )

        for idx, src in enumerate(srcs, start=1):
            # 跳过远程 URL
            if self._is_remote_url(src):
                continue

            # 解析为绝对路径
            try:
                resolved = str((base_dir / src).resolve())
            except (OSError, ValueError):
                resolved = src

            if resolved in seen:
                continue
            seen.add(resolved)

            images.append(
                ImageRef(
                    index=idx,
                    original_path=resolved,
                    alt="",
                    placeholder=f"{{{{IMG_{idx:02d}}}}}",
                )
            )
        return images

    def scan_html(self, html: str, base_dir: Path | None = None) -> list[str]:
        """从 HTML 字符串提取所有图片 src

        Args:
            html: HTML 字符串
            base_dir: 用于解析相对路径的基准目录(可选)

        Returns:
            图片 src 列表(按出现顺序,去重)
        """
        return extract_images(html)

    def check_exists(self, images: list[ImageRef]) -> tuple[list[ImageRef], list[ImageRef]]:
        """检查图片文件是否存在

        Args:
            images: 图片引用列表

        Returns:
            (存在列表, 缺失列表)
        """
        existing: list[ImageRef] = []
        missing: list[ImageRef] = []
        for img in images:
            path = Path(img.original_path)
            if path.exists() and path.is_file():
                existing.append(img)
            else:
                missing.append(img)
        return existing, missing

    def _is_remote_url(self, src: str) -> bool:
        """判断 src 是否为远程 URL 或 data URI"""
        lower = src.lower()
        return (
            lower.startswith("http://")
            or lower.startswith("https://")
            or lower.startswith("//")
            or lower.startswith("data:")
            or lower.startswith("mailto:")
        )
