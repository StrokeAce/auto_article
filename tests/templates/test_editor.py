"""EditorServer 测试

测试纯函数逻辑,不启动真实 HTTP 服务。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aap.templates.editor.server import EditorServer


def test_init_defaults() -> None:
    """默认参数初始化"""
    server = EditorServer()
    assert server.port == 7000
    assert server.template_name is None
    assert server.open_browser is True
    assert server.app is None


def test_init_custom(tmp_path: Path) -> None:
    """自定义参数初始化"""
    sample = tmp_path / "sample.md"
    sample.write_text("# title", encoding="utf-8")
    server = EditorServer(
        port=8000,
        sample_article=sample,
        template_name="custom",
        open_browser=False,
    )
    assert server.port == 8000
    assert server.template_name == "custom"
    assert server.open_browser is False
    assert server.sample_article == sample.resolve()


def test_build_config_from_dict() -> None:
    """从字典构造 TemplateConfig"""
    server = EditorServer()
    data = {
        "name": "test",
        "description": "测试模板",
        "typography": {"font_family": "serif", "base_size": "14px"},
        "spacing": {"paragraph_margin": "10px"},
    }
    config = server._build_config(data, "fallback-name")
    assert config.name == "test"
    assert config.typography.font_family == "serif"
    assert config.spacing.paragraph_margin == "10px"


def test_build_config_uses_name_fallback() -> None:
    """字典中无 name 时使用传入的 fallback name"""
    server = EditorServer()
    data = {"description": "无名称"}
    config = server._build_config(data, "fallback")
    assert config.name == "fallback"


def test_build_config_empty_dict() -> None:
    """空字典也能构造(使用默认子配置)"""
    server = EditorServer()
    config = server._build_config({}, "empty")
    assert config.name == "empty"
    # 子配置使用默认值
    assert config.typography is not None
    assert config.spacing is not None


def test_build_app_creates_fastapi() -> None:
    """_build_app 返回 FastAPI 应用"""
    server = EditorServer(open_browser=False)
    app = server._build_app()
    assert app is not None
    assert app.title == "AAP Template Editor"
    # 应包含路由
    assert len(app.routes) > 0


def test_render_preview_html_with_sample(tmp_path: Path) -> None:
    """使用示例文章渲染预览 HTML"""
    sample = tmp_path / "sample.md"
    sample.write_text(
        "---\ntitle: 测试\ntemplate: minimal\n---\n\n# 标题\n\n正文内容\n",
        encoding="utf-8",
    )
    server = EditorServer(sample_article=sample, open_browser=False)

    from aap.core.models import TemplateConfig
    config = TemplateConfig(name="minimal", description="测试")
    html = server._render_preview_html(config, "section { color: red; }")

    assert "标题" in html
    assert "正文内容" in html
    assert "<section" in html


def test_render_preview_html_missing_sample(tmp_path: Path) -> None:
    """示例文章不存在时抛 FileNotFoundError"""
    server = EditorServer(
        sample_article=tmp_path / "nonexistent.md",
        open_browser=False,
    )
    from aap.core.models import TemplateConfig
    config = TemplateConfig(name="minimal")
    with pytest.raises(FileNotFoundError, match="示例文章不存在"):
        server._render_preview_html(config, "")


def test_render_editor_page_returns_html() -> None:
    """_render_editor_page 返回 HTML 字符串"""
    server = EditorServer(open_browser=False)
    html = server._render_editor_page()
    assert "<!DOCTYPE html>" in html
    assert "AAP 模板编辑器" in html
    assert "template-select" in html
    assert "editor-css" in html
    assert "editor-yaml" in html
