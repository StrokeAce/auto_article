"""HTML 处理工具函数

提供 CSS 内联、不支持标签过滤、图片提取等工具函数。
所有函数均为纯函数,无副作用,可独立单测。
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
import tinycss2

# 微信编辑器支持的标签白名单
SUPPORTED_TAGS: set[str] = {
    "section", "span", "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "sub", "sup",
    "a", "img",
    "ul", "ol", "li",
    "blockquote",
    "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
    "div",  # 兼容容器
}

# 必须移除内容的危险标签(连同内容一起删除)
DANGEROUS_TAGS: set[str] = {
    "script", "iframe", "object", "embed", "form",
    "input", "button", "textarea", "select", "style",
    "link", "meta", "base",
}

# 允许的 HTML 属性白名单(其他属性会被移除)
ALLOWED_ATTRS: dict[str, set[str]] = {
    "*": {"style", "class"},
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height", "data-src"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align"},
    "col": {"width", "align"},
    "colgroup": {"span"},
}


def inline_css(html: str, css: str) -> str:
    """将 CSS 规则内联到 HTML 标签的 style 属性

    解析 CSS 选择器与声明,使用 BeautifulSoup 定位元素并合并 style。
    已存在的 style 属性会保留非冲突部分。

    Args:
        html: 原始 HTML 字符串
        css: CSS 样式文本

    Returns:
        内联样式后的 HTML 字符串
    """
    if not css.strip():
        return html

    rules = _parse_css_rules(css)
    if not rules:
        return html

    soup = BeautifulSoup(html, "lxml")

    for selector, declarations in rules:
        # 跳过复杂选择器(包含伪类/伪元素/@规则)
        if ":" in selector or "::" in selector or selector.startswith("@"):
            continue
        try:
            elements = soup.select(selector)
        except Exception:
            # 选择器语法不支持时跳过
            continue
        for el in elements:
            existing = el.get("style", "")
            merged = _merge_styles(existing, declarations)
            if merged:
                el["style"] = merged

    # 输出时移除 soup 自动添加的 html/body 包裹(若原 HTML 没有这些根标签)
    return _serialize(soup, html)


def filter_unsupported_tags(html: str) -> str:
    """过滤微信编辑器不支持的 HTML 标签

    - 危险标签(script/style/iframe 等):连同内容一起删除
    - 其他不支持标签:unwrap(保留子元素文本内容)
    - 移除不支持的属性
    - 移除 HTML 注释

    Args:
        html: 原始 HTML 字符串

    Returns:
        过滤后的安全 HTML 字符串
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. 移除 HTML 注释
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    # 2. 危险标签连同内容一起删除
    for tag_name in DANGEROUS_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 3. 不支持标签 unwrap(保留子元素)
    for tag in soup.find_all(True):
        if tag.name not in SUPPORTED_TAGS:
            tag.unwrap()

    # 4. 清理不支持的属性
    for tag in soup.find_all(True):
        allowed = _get_allowed_attrs(tag.name)
        attrs_to_remove = [k for k in tag.attrs if k not in allowed]
        for k in attrs_to_remove:
            del tag.attrs[k]

    return _serialize(soup, html)


def extract_images(html: str) -> list[str]:
    """从 HTML 中提取所有图片地址

    按 DOM 顺序返回 <img src="..."> 中的 src 值。

    Args:
        html: HTML 字符串

    Returns:
        图片 URL/路径列表(按出现顺序,去重)
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    result: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if src and src not in seen:
            seen.add(src)
            result.append(src)
    return result


def replace_image_src(html: str, mapping: dict[str, str]) -> str:
    """替换 HTML 中的图片 src

    Args:
        html: 原 HTML
        mapping: {原src: 新src}

    Returns:
        替换后的 HTML
    """
    if not mapping:
        return html
    soup = BeautifulSoup(html, "lxml")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src in mapping:
            img["src"] = mapping[src]
            # 同时更新 data-src 以兼容微信编辑器
            img["data-src"] = mapping[src]
    return _serialize(soup, html)


def wrap_section(html: str, style: Optional[str] = None) -> str:
    """将 HTML 用 <section> 包裹(微信编辑器推荐根标签)

    Args:
        html: 原 HTML
        style: section 的内联样式

    Returns:
        包裹后的 HTML
    """
    style_attr = f' style="{style}"' if style else ""
    return f"<section{style_attr}>\n{html}\n</section>"


# ===== 内部工具函数 =====


def _parse_css_rules(css: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """解析 CSS 文本为 [(selector, [(prop, value), ...]), ...]"""
    rules: list[tuple[str, list[tuple[str, str]]]] = []
    stylesheet = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    for node in stylesheet:
        if node.type != "qualified-rule":
            continue
        # 选择器(去掉前后空白与换行)
        selector = tinycss2.serialize(node.prelude).strip()
        # 声明块
        declarations = tinycss2.parse_declaration_list(
            node.content, skip_comments=True, skip_whitespace=True
        )
        decls: list[tuple[str, str]] = []
        for decl in declarations:
            if decl.type != "declaration":
                continue
            prop = decl.lower_name
            value = tinycss2.serialize(decl.value).strip()
            if prop and value:
                decls.append((prop, value))
        if selector and decls:
            rules.append((selector, decls))
    return rules


def _merge_styles(existing: str, declarations: list[tuple[str, str]]) -> str:
    """合并已有 style 与新声明,新声明优先级高

    Args:
        existing: 已有的 style 字符串,如 "color: red; font-size: 14px;"
        declarations: [(prop, value), ...]

    Returns:
        合并后的 style 字符串
    """
    style_map: dict[str, str] = {}

    # 解析已有 style
    for part in existing.split(";"):
        part = part.strip()
        if ":" in part:
            k, _, v = part.partition(":")
            k = k.strip().lower()
            v = v.strip()
            if k:
                style_map[k] = v

    # 应用新声明(覆盖)
    for prop, value in declarations:
        style_map[prop.lower()] = value

    return "; ".join(f"{k}: {v}" for k, v in style_map.items())


def _get_allowed_attrs(tag_name: str) -> set[str]:
    """获取标签允许的属性集合"""
    base = ALLOWED_ATTRS.get("*", set())
    specific = ALLOWED_ATTRS.get(tag_name, set())
    return base | specific


def _serialize(soup: BeautifulSoup, original_html: str) -> str:
    """序列化 BeautifulSoup,尽量保持原 HTML 的根结构

    若原 HTML 没有 <html>/<body> 包裹,则只返回 body 内容。
    """
    # 检测原 HTML 是否包含 html/body 标签
    has_html_root = bool(re.search(r"<html", original_html, re.IGNORECASE))
    has_body_root = bool(re.search(r"<body", original_html, re.IGNORECASE))

    if has_html_root or has_body_root:
        return str(soup)

    # 原 HTML 是片段:提取 body 子元素
    body = soup.body if soup.body else soup
    parts: list[str] = []
    for child in body.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text.strip():
                parts.append(text)
        elif isinstance(child, Tag):
            parts.append(str(child))
    return "\n".join(parts)
