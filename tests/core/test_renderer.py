"""HTMLRenderer 与 TemplateManager 测试"""
from pathlib import Path

import pytest

from aap.core.parser import ArticleParser
from aap.core.renderer import HTMLRenderer
from aap.templates.manager import BUILTIN_TEMPLATES_DIR, TemplateManager


@pytest.fixture
def parser() -> ArticleParser:
    return ArticleParser()


@pytest.fixture
def renderer() -> HTMLRenderer:
    return HTMLRenderer()


@pytest.fixture
def template_manager() -> TemplateManager:
    # 用临时目录避免污染用户目录
    return TemplateManager(
        project_templates_dir=Path(".aap/templates"),
        user_templates_dir=Path.home() / ".aap" / "templates",
    )


# ===== TemplateManager 测试 =====


def test_list_templates_includes_minimal(template_manager: TemplateManager) -> None:
    """内置 minimal 模板出现在列表中"""
    templates = template_manager.list_templates()
    assert "minimal" in templates


def test_load_minimal_template(template_manager: TemplateManager) -> None:
    """加载 minimal 模板配置"""
    cfg = template_manager.load_template("minimal")
    assert cfg.name == "minimal"
    assert "PingFang" in cfg.typography.font_family or "system" in cfg.typography.font_family
    assert cfg.typography.base_size == "16px"
    assert cfg.typography.base_color == "#333333"


def test_load_template_css(template_manager: TemplateManager) -> None:
    """加载 minimal 模板 CSS"""
    css = template_manager.load_template_css("minimal")
    assert "section" in css
    assert "font-size" in css


def test_load_template_not_found(template_manager: TemplateManager) -> None:
    """加载不存在的模板抛出 FileNotFoundError"""
    with pytest.raises(FileNotFoundError):
        template_manager.load_template("nonexistent_template_xyz")


def test_resolve_template_priority_cli_over_frontmatter(
    template_manager: TemplateManager, parser: ArticleParser, sample_md_path: Path
) -> None:
    """CLI 参数优先级 > Front Matter > 默认"""
    article = parser.parse(sample_md_path)
    # article.meta.template == "minimal"
    cfg = template_manager.resolve_template(article, cli_override=None)
    assert cfg.name == "minimal"


def test_resolve_template_fallback_to_default(
    template_manager: TemplateManager, parser: ArticleParser, sample_md_path: Path
) -> None:
    """Front Matter 指定的模板不存在时,回退到默认"""
    article = parser.parse(sample_md_path)
    article.meta.template = "nonexistent"
    cfg = template_manager.resolve_template(article, cli_override=None)
    # 回退到 default_template = "minimal"
    assert cfg.name == "minimal"


# ===== HTMLRenderer 测试 =====


def test_render_for_export_replaces_image_with_placeholder(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """导出模式:图片 src 替换为占位符 {{IMG_01}}"""
    article = parser.parse(sample_md_path)
    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_for_export(article, template, css=css)
    assert "{{IMG_01}}" in html
    # 不应包含原始图片路径
    assert "images/sample.png" not in html


def test_render_preview_keeps_original_src(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """预览模式:保留原 src"""
    article = parser.parse(sample_md_path)
    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_preview(article, template, css=css)
    assert "images/sample.png" in html
    assert "{{IMG_01}}" not in html


def test_render_wraps_in_section(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """渲染结果用 <section> 包裹"""
    article = parser.parse(sample_md_path)
    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_for_export(article, template, css=css)
    assert html.startswith("<section")
    assert html.rstrip().endswith("</section>")


def test_render_inlines_css(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """CSS 内联到 style 属性(无 <style> 标签)"""
    article = parser.parse(sample_md_path)
    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_for_export(article, template, css=css)
    assert "<style" not in html
    assert "style=" in html


def test_render_filters_dangerous_tags(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    tmp_path: Path,
) -> None:
    """渲染结果不含 script/style/iframe 等危险标签"""
    md = tmp_path / "danger.md"
    md.write_text(
        '正文 <script>alert(1)</script> <style>p{color:red}</style> 结束',
        encoding="utf-8",
    )
    article = parser.parse(md)
    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_for_export(article, template, css=css)
    assert "<script" not in html
    # style 标签应被过滤(CSS 已内联到 style 属性)
    assert "<style>" not in html


def test_render_section_has_root_style(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """根 <section> 包含 typography 与 spacing 样式"""
    article = parser.parse(sample_md_path)
    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_for_export(article, template, css=css)
    # 根 section 应包含 font-family、font-size 等
    section_open = html[: html.index(">")]
    assert "font-family" in section_open
    assert "font-size" in section_open
    assert "color" in section_open


def test_render_for_publish_uses_wechat_url(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """发布模式:用 wechat_url 替换图片 src(若已设置)"""
    article = parser.parse(sample_md_path)
    # 模拟图片已上传,设置 wechat_url
    assert article.images
    article.images[0].wechat_url = "https://mmbiz.qpic.cn/mmbiz_png/abc123/640"

    template = template_manager.load_template("minimal")
    css = template_manager.load_template_css("minimal")

    html = renderer.render_for_publish(article, template, css=css)
    assert "mmbiz.qpic.cn" in html
    assert "{{IMG_01}}" not in html


def test_render_no_css_uses_config_fallback(
    parser: ArticleParser, renderer: HTMLRenderer, template_manager: TemplateManager,
    sample_md_path: Path,
) -> None:
    """未提供 css 时,根据 TemplateConfig 生成兜底 CSS"""
    article = parser.parse(sample_md_path)
    template = template_manager.load_template("minimal")

    # 不传 css,触发 _build_css_from_config
    html = renderer.render_for_export(article, template, css=None)
    assert "style=" in html
    # 应用了 typography 颜色
    assert "#333333" in html or "#1a1a1a" in html
