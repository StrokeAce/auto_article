"""HTML 渲染器

将 Article 渲染为带内联样式的 HTML,适配微信编辑器。

渲染流程:
1. 应用模板 CSS(内联到 style 属性)
2. 过滤微信不支持的标签与属性
3. 图片 src 替换:
   - 模式 placeholder: 用占位符 {{IMG_01}} 替换本地 src
   - 模式 url:        用 ImageRef.wechat_url 替换(已上传)
   - 模式 keep:       保留原 src(用于本地预览)
4. 章节标题装饰:若设置了 chapter_icon_url,将 H1 替换为图片+文字的居中结构
5. 用 <section> 包裹,注入根样式(typography/spacing)
"""
from __future__ import annotations

import re
from typing import Optional

from aap.core.html_utils import (
    filter_unsupported_tags,
    inline_css,
    replace_image_src,
    wrap_section,
)
from aap.core.models import Article, TemplateConfig


class HTMLRenderer:
    """HTML 渲染器

    负责将文章 HTML 与模板样式结合,生成微信兼容的内联样式 HTML。
    """

    # 图片 src 替换模式
    MODE_PLACEHOLDER = "placeholder"  # 用 {{IMG_01}} 替换(导出场景)
    MODE_URL = "url"                  # 用微信 URL 替换(发布后场景)
    MODE_KEEP = "keep"                # 保留原 src(本地预览场景)

    def render(
        self,
        article: Article,
        template: TemplateConfig,
        css: Optional[str] = None,
        image_mode: str = MODE_PLACEHOLDER,
        chapter_icon_url: str = "",
        chapter_title_urls: Optional[list[str]] = None,
    ) -> str:
        """渲染文章为带内联样式的 HTML

        Args:
            article: 文章对象
            template: 模板配置
            css: 模板 CSS 文本(若为 None,则根据 template 配置生成默认 CSS)
            image_mode: 图片 src 替换模式
            chapter_icon_url: 章节标题装饰小图标 URL(所有章节共用,旧模式)
            chapter_title_urls: 章节标题整图 URL 列表(按 H1 出现顺序匹配,新模式)
                优先级高于 chapter_icon_url

        Returns:
            微信编辑器可粘贴的 HTML 字符串
        """
        # 1. 准备 CSS
        if css is None:
            css = self._build_css_from_config(template)

        # 2. 图片 src 替换
        html = self._replace_images(article.content_html, article, image_mode)

        # 3. 过滤不支持标签
        html = filter_unsupported_tags(html)

        # 4. 内联 CSS
        html = inline_css(html, css)

        # 5. 章节标题装饰
        #    优先级: 整图模式 > 单图标模式 > 不装饰
        if chapter_title_urls:
            html = self._replace_chapter_titles_with_images(
                html, chapter_title_urls, template
            )
        elif chapter_icon_url:
            html = self._decorate_chapter_titles(html, chapter_icon_url, template)

        # 5.5 将 H2-H6 转换为 <p> 标签(保留内联样式)
        #     微信编辑器对 h1-h6 有内置默认 font-size,粘贴时会覆盖我们的内联样式
        #     导致"一、二、三""1、2、3"等子标题显示为 16px 而非 15px
        #     这些子标题本质就是正文,改用 <p> 标签可完全规避字号问题
        #     注意:H1 不转换(已被章节标题装饰逻辑处理)
        html = self._convert_subheadings_to_paragraphs(html)

        # 6. 用 section 包裹,注入根样式
        root_style = self._build_root_style(template)
        html = wrap_section(html, root_style)

        return html

    def render_preview(
        self,
        article: Article,
        template: TemplateConfig,
        css: Optional[str] = None,
        chapter_icon_url: str = "",
        chapter_title_urls: Optional[list[str]] = None,
    ) -> str:
        """渲染用于本地预览的 HTML(保留原图片 src,可访问本地图片)"""
        return self.render(
            article, template, css=css,
            image_mode=self.MODE_KEEP,
            chapter_icon_url=chapter_icon_url,
            chapter_title_urls=chapter_title_urls,
        )

    def render_for_export(
        self,
        article: Article,
        template: TemplateConfig,
        css: Optional[str] = None,
        chapter_icon_url: str = "",
        chapter_title_urls: Optional[list[str]] = None,
    ) -> str:
        """渲染用于手动导出/复制的 HTML(图片用占位符,便于人工替换)"""
        return self.render(
            article, template, css=css,
            image_mode=self.MODE_PLACEHOLDER,
            chapter_icon_url=chapter_icon_url,
            chapter_title_urls=chapter_title_urls,
        )

    def render_for_publish(
        self,
        article: Article,
        template: TemplateConfig,
        css: Optional[str] = None,
        chapter_icon_url: str = "",
        chapter_title_urls: Optional[list[str]] = None,
    ) -> str:
        """渲染用于 API 发布的 HTML(图片用微信 URL)"""
        return self.render(
            article, template, css=css,
            image_mode=self.MODE_URL,
            chapter_icon_url=chapter_icon_url,
            chapter_title_urls=chapter_title_urls,
        )

    # ===== 章节标题装饰 =====

    # 匹配 <h1>标题</h1>(含可能的属性)
    _H1_PATTERN = re.compile(
        r'<h1(?:\s[^>]*)?>(.*?)</h1>',
        re.IGNORECASE | re.DOTALL,
    )

    # 匹配 <hN attrs>content</hN>(N=2~6),用于将子标题转换为段落
    _SUBHEADING_PATTERN = re.compile(
        r'<(h[2-6])((?:\s[^>]*)?)>(.*?)</\1>',
        re.IGNORECASE | re.DOTALL,
    )

    def _convert_subheadings_to_paragraphs(self, html: str) -> str:
        """将 h2-h6 子标题标签转换为 <p> 标签(保留内联样式)

        微信编辑器对 h1-h6 有内置默认 font-size,粘贴时会覆盖我们的内联样式,
        导致"一、二、三""1、2、3"等子标题显示为 16px 而非 15px。
        这些子标题本质就是正文段落,改用 <p> 标签可完全规避字号问题。

        注意:
        - 此方法在 inline_css 之后执行,此时 h* 标签已带内联样式,转换后样式完整保留
        - H1 不转换(已被章节标题装饰逻辑处理为图片+文字结构)
        """
        def _replace(match: re.Match) -> str:
            attrs = match.group(2) or ""
            content = match.group(3)
            return f'<p{attrs}>{content}</p>'

        return self._SUBHEADING_PATTERN.sub(_replace, html)

    def _replace_chapter_titles_with_images(
        self, html: str, image_urls: list[str], template: TemplateConfig
    ) -> str:
        """将 H1 按出现顺序替换为整图+文字标题(第 N 个 H1 用第 N 张图)

        替换后结构(图片在上,文字标题在下,均居中):
        <section style="text-align: center; margin: 24px 0;">
          <img src="URL" style="max-width: 100%; width: 100%; height: auto; border: none; display: block; margin: 0 auto;">
          <span style="color: HEADING_COLOR; font-weight: bold; font-size: 16px; letter-spacing: 0.578px; display: block; margin-top: 8px;">标题文字</span>
        </section>
        """
        heading_color = template.typography.heading_color or "rgb(40, 77, 142)"
        counter = [0]  # 用列表包装,闭包内可修改

        def _replace(match: re.Match) -> str:
            idx = counter[0]
            counter[0] += 1
            if idx >= len(image_urls):
                # 图片不够,保留原 H1
                return match.group(0)
            url = image_urls[idx]
            title_text = match.group(1).strip()
            return (
                f'<section style="text-align: center; margin: 24px 0;">'
                f'<img src="{url}" style="max-width: 100%; width: 100%; '
                f'height: auto; border: none; display: block; margin: 0 auto;">'
                f'<span style="color: {heading_color}; font-weight: bold; '
                f'font-size: 16px; letter-spacing: 0.578px; display: block; '
                f'margin-top: 8px;">{title_text}</span>'
                f'</section>'
            )

        return self._H1_PATTERN.sub(_replace, html)

    def _decorate_chapter_titles(
        self, html: str, icon_url: str, template: TemplateConfig
    ) -> str:
        """将 H1 替换为图片+文字的居中 section(旧模式,单图标共用)

        替换后结构:
        <section style="text-align: center; margin: 24px 0;">
          <img src="ICON" style="vertical-align: middle; width: 16px; height: 16px; margin-right: 8px;">
          <span style="color: HEADING_COLOR; font-weight: bold; font-size: 16px; vertical-align: middle;">标题</span>
        </section>
        """
        heading_color = template.typography.heading_color or "rgb(40, 77, 142)"

        def _replace(match: re.Match) -> str:
            title_text = match.group(1).strip()
            return (
                f'<section style="text-align: center; margin: 24px 0;">'
                f'<img src="{icon_url}" style="vertical-align: middle; '
                f'width: 16px; height: 16px; margin-right: 8px; border: none;">'
                f'<span style="color: {heading_color}; font-weight: bold; '
                f'font-size: 16px; vertical-align: middle; letter-spacing: 0.578px;">'
                f'{title_text}</span>'
                f'</section>'
            )

        return self._H1_PATTERN.sub(_replace, html)

    # ===== 内部方法 =====

    def _replace_images(self, html: str, article: Article, mode: str) -> str:
        """根据模式替换 HTML 中的图片 src"""
        if not article.images:
            return html

        if mode == self.MODE_KEEP:
            return html

        # 构建 {原src: 新src} 映射
        mapping: dict[str, str] = {}
        for img in article.images:
            # 原始 src 可能是相对路径,需要兼容匹配
            original_src = self._extract_relative_src(img.original_path, article.source_path)
            if mode == self.MODE_PLACEHOLDER:
                new_src = img.placeholder
            elif mode == self.MODE_URL:
                new_src = img.wechat_url or img.placeholder
            else:
                continue

            if original_src:
                mapping[original_src] = new_src
            # 也用绝对路径作为键,以防万一
            mapping[img.original_path] = new_src

        return replace_image_src(html, mapping)

    def _extract_relative_src(self, abs_path: str, source_path: Optional[object]) -> str:
        """从绝对路径反推 Markdown 中可能使用的相对 src

        由于 parser 已经把相对路径转绝对,这里需要还原以匹配 HTML 中的 src。
        """
        if source_path is None:
            return abs_path
        try:
            from pathlib import Path
            src_path = Path(source_path)
            abs_p = Path(abs_path)
            try:
                rel = abs_p.relative_to(src_path.parent)
                # 优先返回正斜杠形式(Markdown 中常见)
                return str(rel).replace("\\", "/")
            except ValueError:
                return abs_path
        except Exception:
            return abs_path

    def _build_root_style(self, template: TemplateConfig) -> str:
        """构造根 <section> 的内联样式"""
        parts: list[str] = []
        t = template.typography
        s = template.spacing

        if t.font_family:
            parts.append(f"font-family: {t.font_family}")
        if t.base_size:
            parts.append(f"font-size: {t.base_size}")
        if t.base_color:
            parts.append(f"color: {t.base_color}")
        if t.line_height:
            parts.append(f"line-height: {t.line_height}")
        if s.left_right_padding:
            parts.append(f"padding: 0 {s.left_right_padding}")
        if s.background_color:
            parts.append(f"background-color: {s.background_color}")

        return "; ".join(parts)

    def _build_css_from_config(self, template: TemplateConfig) -> str:
        """根据 TemplateConfig 生成兜底 CSS(当模板没有 style.css 时使用)"""
        t = template.typography
        s = template.spacing
        img = template.image
        tbl = template.table
        cb = template.code_block

        lines: list[str] = []

        # 标题
        h_rules: list[str] = []
        if t.heading_color:
            h_rules.append(f"color: {t.heading_color}")
        h_rules.append("font-weight: bold")
        h_rules.append("margin: 24px 0 16px")
        if h_rules:
            lines.append(f"h1, h2, h3, h4, h5, h6 {{ {'; '.join(h_rules)} }}")

        # 段落
        p_rules: list[str] = []
        if s.paragraph_margin:
            p_rules.append(f"margin: {s.paragraph_margin} 0")
        if s.first_line_indent and s.first_line_indent != "0":
            p_rules.append(f"text-indent: {s.first_line_indent}")
        if p_rules:
            lines.append(f"p {{ {'; '.join(p_rules)} }}")

        # 链接
        if t.link_color:
            lines.append(f"a {{ color: {t.link_color}; text-decoration: none }}")

        # 图片
        img_rules: list[str] = []
        if img.max_width:
            img_rules.append(f"max-width: {img.max_width}")
        if img.border_radius:
            img_rules.append(f"border-radius: {img.border_radius}")
        if img_rules:
            lines.append(f"img {{ {'; '.join(img_rules)} }}")

        # 行内代码
        code_rules: list[str] = []
        if t.code_color:
            code_rules.append(f"color: {t.code_color}")
        code_rules.append("background-color: #f9f2f4")
        code_rules.append("padding: 2px 4px")
        code_rules.append("border-radius: 3px")
        if cb.font_size:
            code_rules.append(f"font-size: {cb.font_size}")
        lines.append(f"code {{ {'; '.join(code_rules)} }}")

        # 代码块
        pre_rules: list[str] = []
        if cb.background:
            pre_rules.append(f"background-color: {cb.background}")
        pre_rules.append("padding: 16px")
        pre_rules.append("border-radius: 6px")
        pre_rules.append("overflow-x: auto")
        if cb.font_size:
            pre_rules.append(f"font-size: {cb.font_size}")
        lines.append(f"pre {{ {'; '.join(pre_rules)} }}")

        # 表格
        lines.append("table { width: 100%; border-collapse: collapse }")
        td_rules: list[str] = []
        if tbl.border_color:
            td_rules.append(f"border: 1px solid {tbl.border_color}")
        td_rules.append("padding: 8px 12px")
        lines.append(f"th, td {{ {'; '.join(td_rules)} }}")

        if tbl.header_background:
            lines.append(f"th {{ background-color: {tbl.header_background} }}")
        if tbl.zebra_striped and tbl.zebra_color:
            lines.append(f"tr:nth-child(even) {{ background-color: {tbl.zebra_color} }}")

        # 引用
        lines.append(
            "blockquote { border-left: 4px solid #dddddd; padding-left: 12px; "
            "color: #888888; margin: 16px 0 }"
        )

        return "\n".join(lines)
