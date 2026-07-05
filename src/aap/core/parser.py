"""文章解析器

将 Markdown 文件解析为 Article 对象,分离 YAML Front Matter 与正文。
- 使用 python-frontmatter 分离 YAML 元信息
- 使用 markdown-it-py 渲染正文为 HTML
- 扫描正文中的图片引用,生成 ImageRef 列表
"""
from __future__ import annotations

import re
from pathlib import Path

import frontmatter
from markdown_it import MarkdownIt

from aap.core.models import Article, ArticleMeta, ImageRef


class ArticleParser:
    """Markdown 文章解析器

    使用 python-frontmatter 分离 YAML 元信息,
    使用 markdown-it-py 将正文渲染为 HTML。
    """

    def __init__(self) -> None:
        # 配置 markdown-it-py
        # - html: True 允许原始 HTML(图片标签、特殊排版)
        # - linkify: 自动识别链接
        # - typographer: 智能引号(可选,默认关闭以保持源文本)
        # - breaks: 换行符转换为 <br>(保持 Markdown 源码换行语义)
        self._md = MarkdownIt("commonmark", {"html": True, "linkify": True, "breaks": False})
        self._md.enable(["table", "strikethrough"])

    def parse(self, md_path: Path) -> Article:
        """解析 Markdown 文件,返回 Article 对象

        Args:
            md_path: Markdown 文件路径

        Returns:
            Article 对象,包含元信息与渲染后的 HTML 内容

        Raises:
            FileNotFoundError: 文件不存在
        """
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown 文件不存在: {md_path}")

        md_path = md_path.resolve()
        raw_text = md_path.read_text(encoding="utf-8")

        # 分离 Front Matter 与正文
        post = frontmatter.loads(raw_text)
        meta = self._extract_meta(post.metadata)
        content = post.content

        # 渲染为 HTML
        content_html = self._md.render(content)

        # 扫描图片引用
        images = self._scan_images(content_html, md_path)

        # 若 Front Matter 未指定 title,尝试从正文第一个标题提取
        if not meta.title:
            title = self._extract_first_heading(content)
            if title:
                meta.title = title
            else:
                meta.title = md_path.stem

        return Article(
            meta=meta,
            content_html=content_html,
            source_path=md_path,
            images=images,
        )

    def _extract_meta(self, front_matter: dict) -> ArticleMeta:
        """从 Front Matter 字典构造文章元信息

        Args:
            front_matter: Front Matter 字典

        Returns:
            ArticleMeta 对象
        """
        # 处理 tags 字段(支持 list 或逗号分隔字符串)
        tags_value = front_matter.get("tags", [])
        if isinstance(tags_value, str):
            tags = [t.strip() for t in tags_value.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in tags_value if t]

        return ArticleMeta(
            title=str(front_matter.get("title", "")).strip(),
            author=str(front_matter.get("author", "")).strip(),
            summary=str(front_matter.get("summary", "")).strip(),
            cover=str(front_matter.get("cover", "")).strip(),
            tags=tags,
            template=str(front_matter.get("template", "")).strip(),
            category=str(front_matter.get("category", "")).strip(),
        )

    def _scan_images(self, html: str, md_path: Path) -> list[ImageRef]:
        """从 HTML 内容扫描图片引用,返回 ImageRef 列表

        Args:
            html: 渲染后的 HTML
            md_path: Markdown 源文件路径(用于解析相对路径)

        Returns:
            ImageRef 列表,按出现顺序
        """
        from bs4 import BeautifulSoup

        images: list[ImageRef] = []
        seen_paths: set[str] = set()
        base_dir = md_path.parent

        soup = BeautifulSoup(html, "lxml")
        for idx, img_tag in enumerate(soup.find_all("img"), start=1):
            src = img_tag.get("src", "") or img_tag.get("data-src", "")
            alt = img_tag.get("alt", "") or ""
            if not src:
                continue

            # 跳过 http(s) URL、data URI 等非本地路径
            if self._is_remote_url(src):
                continue

            # 解析为绝对路径(字符串形式,便于序列化)
            try:
                resolved = (base_dir / src).resolve()
                original_path = str(resolved)
            except (OSError, ValueError):
                original_path = src

            # 去重(同一图片多次引用只算一张)
            if original_path in seen_paths:
                continue
            seen_paths.add(original_path)

            placeholder = self._make_placeholder(idx)
            images.append(
                ImageRef(
                    index=idx,
                    original_path=original_path,
                    alt=alt,
                    placeholder=placeholder,
                )
            )
        return images

    def _extract_first_heading(self, markdown_text: str) -> str:
        """从 Markdown 文本提取第一个标题文本

        Args:
            markdown_text: Markdown 源文本

        Returns:
            第一个标题的纯文本(无 # 号),无则返回空字符串
        """
        # 匹配 # 开头的标题(支持 1-6 级)
        pattern = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
        match = pattern.search(markdown_text)
        if match:
            # 去掉内联 Markdown 标记(**、*、`、链接等)
            text = match.group(2)
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
            text = re.sub(r"\*([^*]+)\*", r"\1", text)
            text = re.sub(r"`([^`]+)`", r"\1", text)
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
            return text.strip()
        return ""

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

    def _make_placeholder(self, index: int) -> str:
        """生成图片占位符,如 {{IMG_01}}"""
        return f"{{{{IMG_{index:02d}}}}}"
