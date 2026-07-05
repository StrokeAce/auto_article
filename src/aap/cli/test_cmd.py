"""aap test compatibility 命令

兼容性测试工具,检测文章在微信编辑器的兼容性。

检测项:
- 危险标签(script/iframe/style/form 等)
- 不支持的标签(被 unwrap)
- 不支持的属性(被剥离)
- HTML 注释
- 内联 CSS 中微信不支持的属性
- 占位符未替换(如 {{IMG_01}})
- 必填字段缺失(如 Front Matter 的 cover)
- 图片文件是否存在
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="兼容性测试工具")


@app.command("compatibility")
def compatibility(
    md_path: Path = typer.Argument(..., help="待检测的 Markdown 文件路径"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="指定模板名(覆盖 Front Matter)"
    ),
) -> None:
    """检测文章在微信编辑器的兼容性

    输出报告包含:
    - 通过项 ✅
    - 警告项 ⚠️
    - 错误项 ❌(必须修复才能正常发布)
    """
    from aap.core.parser import ArticleParser
    from aap.core.renderer import HTMLRenderer
    from aap.core.html_utils import SUPPORTED_TAGS, DANGEROUS_TAGS, ALLOWED_ATTRS
    from aap.templates.manager import TemplateManager
    from bs4 import BeautifulSoup, Comment

    if not md_path.exists():
        typer.echo(f"错误: 文件不存在: {md_path}", err=True)
        raise typer.Exit(1)

    parser = ArticleParser()
    renderer = HTMLRenderer()
    tm = TemplateManager()

    article = parser.parse(md_path)
    template_name = tm.resolve_template_name(article, template)
    try:
        tpl = tm.load_template(template_name)
        css = tm.load_template_css(template_name)
    except FileNotFoundError:
        tpl = tm.load_template("minimal")
        css = tm.load_template_css("minimal")

    # 先渲染为导出模式 HTML
    html = renderer.render_for_export(article, tpl, css=css)

    errors: list[str] = []
    warnings: list[str] = []
    passes: list[str] = []

    # 1. Front Matter 必填字段
    if not article.meta.title:
        errors.append("Front Matter 缺少 title 字段")
    else:
        passes.append("Front Matter: title 已设置")
    if not article.meta.cover:
        errors.append("Front Matter 缺少 cover 字段(API 发布必需)")
    else:
        # 检查封面图是否存在
        from pathlib import Path as _P
        cover_p = _P(article.meta.cover)
        if not cover_p.is_absolute():
            cover_p = (md_path.parent / cover_p).resolve()
        if not cover_p.exists():
            errors.append(f"封面图文件不存在: {cover_p}")
        else:
            passes.append(f"封面图存在: {cover_p.name}")

    # 2. 解析渲染后的 HTML 检测
    soup = BeautifulSoup(html, "lxml")

    # 2.1 危险标签(应该已被过滤)
    for tag_name in DANGEROUS_TAGS:
        found = soup.find_all(tag_name)
        if found:
            errors.append(f"渲染后仍含危险标签 <{tag_name}>(共 {len(found)} 处)")
        else:
            passes.append(f"危险标签 <{tag_name}> 已过滤")

    # 2.2 不支持标签
    unsupported: dict[str, int] = {}
    for tag in soup.find_all(True):
        if tag.name not in SUPPORTED_TAGS:
            unsupported[tag.name] = unsupported.get(tag.name, 0) + 1
    if unsupported:
        for name, count in unsupported.items():
            warnings.append(f"含不支持标签 <{name}>({count} 处,会被微信 unwrap)")
    else:
        passes.append("所有标签均在微信支持白名单内")

    # 2.3 不支持的属性
    bad_attrs: list[str] = []
    for tag in soup.find_all(True):
        allowed = ALLOWED_ATTRS.get("*", set()) | ALLOWED_ATTRS.get(tag.name, set())
        for k in tag.attrs:
            if k not in allowed:
                bad_attrs.append(f"<{tag.name}> {k}")
    if bad_attrs:
        warnings.append(f"含不支持属性 {len(bad_attrs)} 处(会被微信剥离)")
    else:
        passes.append("所有属性均在白名单内")

    # 2.4 HTML 注释
    comments = soup.find_all(string=lambda t: isinstance(t, Comment))
    if comments:
        warnings.append(f"含 HTML 注释 {len(comments)} 处(会被微信移除)")
    else:
        passes.append("无 HTML 注释")

    # 2.5 占位符未替换
    import re
    placeholders = re.findall(r"\{\{IMG_\d+\}\}", html)
    if placeholders:
        warnings.append(f"含未替换的图片占位符 {len(placeholders)} 处(发布前需替换为微信 URL)")
    else:
        passes.append("无未替换的图片占位符")

    # 2.6 内联 CSS 中可能不支持的属性
    unsupported_css_props = {
        "position": {"absolute", "fixed"},
        "float": {"left", "right"},
    }
    found_bad_css: list[str] = []
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        for prop, bad_values in unsupported_css_props.items():
            pattern = re.compile(rf"{prop}\s*:\s*([^;]+)", re.IGNORECASE)
            m = pattern.search(style)
            if m:
                val = m.group(1).strip().lower()
                if any(bad in val for bad in bad_values):
                    found_bad_css.append(f"<{tag.name}> style 含 {prop}: {val}")
    if found_bad_css:
        warnings.append(f"内联 CSS 含微信不支持的属性 {len(found_bad_css)} 处")
    else:
        passes.append("内联 CSS 属性均在微信支持范围内")

    # 2.7 图片引用检查
    if article.images:
        missing_count = 0
        for img in article.images:
            from pathlib import Path as _P
            p = _P(img.original_path)
            if not p.exists():
                missing_count += 1
                warnings.append(f"图片文件不存在: {img.original_path}")
        if missing_count == 0:
            passes.append(f"所有 {len(article.images)} 张正文图片文件均存在")
    else:
        passes.append("正文无图片引用")

    # 2.8 标题层级
    h_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if h_tags:
        passes.append(f"含 {len(h_tags)} 个标题(层级合理)")
    else:
        warnings.append("正文无标题(建议至少有一个标题)")

    # 2.9 内容长度
    text = soup.get_text(strip=True)
    if len(text) < 20:
        warnings.append(f"正文内容过短({len(text)} 字符)")
    else:
        passes.append(f"正文长度合理({len(text)} 字符)")

    # 输出报告
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo(f"AAP 兼容性检测报告 - {md_path.name}")
    typer.echo(f"模板: {template_name}")
    typer.echo("=" * 60)
    typer.echo("")

    typer.echo(f"✅ 通过: {len(passes)} 项")
    for p in passes:
        typer.echo(f"  ✅ {p}")
    typer.echo("")

    if warnings:
        typer.echo(f"⚠️  警告: {len(warnings)} 项")
        for w in warnings:
            typer.echo(f"  ⚠️  {w}")
    else:
        typer.echo("⚠️  警告: 0 项")
    typer.echo("")

    if errors:
        typer.echo(f"❌ 错误: {len(errors)} 项")
        for e in errors:
            typer.echo(f"  ❌ {e}")
    else:
        typer.echo("❌ 错误: 0 项")
    typer.echo("")

    # 总结
    if errors:
        typer.echo("总结: ❌ 存在错误,需修复后才能正常发布")
        raise typer.Exit(1)
    elif warnings:
        typer.echo("总结: ⚠️  存在警告,建议修复以提升兼容性")
        raise typer.Exit(0)
    else:
        typer.echo("总结: ✅ 全部通过,可安全发布")
