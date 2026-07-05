"""TemplateEngine Jinja2 封装测试"""
from pathlib import Path

import pytest

from aap.core.template_engine import TemplateEngine


def test_render_string_basic() -> None:
    """render_string 渲染简单字符串模板"""
    engine = TemplateEngine()
    result = engine.render_string("Hello, {{ name }}!", {"name": "AAP"})
    assert result == "Hello, AAP!"


def test_render_string_with_loop() -> None:
    """render_string 支持 for 循环"""
    engine = TemplateEngine()
    template = "{% for item in items %}{{ item }}{% if not loop.last %},{% endif %}{% endfor %}"
    result = engine.render_string(template, {"items": ["a", "b", "c"]})
    assert result == "a,b,c"


def test_render_string_with_conditional() -> None:
    """render_string 支持 if 条件"""
    engine = TemplateEngine()
    template = "{% if ok %}yes{% else %}no{% endif %}"
    assert engine.render_string(template, {"ok": True}) == "yes"
    assert engine.render_string(template, {"ok": False}) == "no"


def test_autoescape_enabled_by_default() -> None:
    """默认开启 HTML 自动转义"""
    engine = TemplateEngine()
    result = engine.render_string("{{ x }}", {"x": "<script>alert(1)</script>"})
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_autoescape_disabled() -> None:
    """关闭自动转义时保留原始 HTML"""
    engine = TemplateEngine(autoescape=False)
    result = engine.render_string("{{ x }}", {"x": "<b>bold</b>"})
    assert result == "<b>bold</b>"


def test_add_template_and_render(tmp_path: Path) -> None:
    """动态添加模板后可渲染"""
    engine = TemplateEngine(template_dir=tmp_path)
    engine.add_template("greet.txt", "Hi, {{ name }}!")
    assert engine.has_template("greet.txt")
    result = engine.render("greet.txt", {"name": "Tom"})
    assert result == "Hi, Tom!"


def test_has_template_false(tmp_path: Path) -> None:
    """不存在的模板返回 False"""
    engine = TemplateEngine(template_dir=tmp_path)
    assert not engine.has_template("nonexistent.txt")


def test_list_templates_includes_dynamic(tmp_path: Path) -> None:
    """list_templates 包含动态添加的模板"""
    engine = TemplateEngine(template_dir=tmp_path)
    engine.add_template("a.txt", "x")
    engine.add_template("b.txt", "y")
    names = engine.list_templates()
    assert "a.txt" in names
    assert "b.txt" in names


def test_init_with_nonexistent_dir(tmp_path: Path) -> None:
    """目录不存在时初始化不报错(有 DictLoader 兜底)"""
    nonexistent = tmp_path / "no_such_dir"
    engine = TemplateEngine(template_dir=nonexistent)
    # 仍可渲染字符串模板
    assert engine.render_string("{{ x }}", {"x": "ok"}) == "ok"


def test_render_from_file(tmp_path: Path) -> None:
    """从文件系统加载模板并渲染"""
    template_file = tmp_path / "hello.txt"
    template_file.write_text("Hello, {{ name }}!", encoding="utf-8")

    engine = TemplateEngine(template_dir=tmp_path)
    assert engine.has_template("hello.txt")
    result = engine.render("hello.txt", {"name": "World"})
    assert result == "Hello, World!"
