"""TemplateManager 测试"""
from pathlib import Path

import pytest
import yaml

from aap.core.models import TemplateConfig
from aap.templates.manager import TemplateManager


def test_list_templates_includes_builtin() -> None:
    """list_templates 至少包含内置 minimal 模板"""
    manager = TemplateManager()
    names = manager.list_templates()
    assert "minimal" in names


def test_load_builtin_minimal() -> None:
    """加载内置 minimal 模板配置"""
    manager = TemplateManager()
    config = manager.load_template("minimal")
    assert config.name == "minimal"
    assert config.typography.font_family  # 非空
    assert config.typography.base_size


def test_load_template_css_minimal() -> None:
    """加载 minimal 模板的 CSS"""
    manager = TemplateManager()
    css = manager.load_template_css("minimal")
    assert "section" in css
    assert "font-family" in css


def test_load_template_not_found() -> None:
    """加载不存在的模板抛 FileNotFoundError"""
    manager = TemplateManager()
    with pytest.raises(FileNotFoundError):
        manager.load_template("nonexistent-template-xyz")


def test_load_template_css_not_found() -> None:
    """加载不存在模板的 CSS 抛 FileNotFoundError"""
    manager = TemplateManager()
    with pytest.raises(FileNotFoundError):
        manager.load_template_css("nonexistent-template-xyz")


def test_save_template_to_user_dir(tmp_path: Path) -> None:
    """保存模板到指定用户目录"""
    user_dir = tmp_path / "templates"
    manager = TemplateManager(user_templates_dir=user_dir)

    config = TemplateConfig(name="custom", description="测试")
    css = "section { color: red; }"

    saved_path = manager.save_template("custom", config, css)

    assert saved_path.exists()
    assert (saved_path / "template.yaml").exists()
    assert (saved_path / "style.css").exists()

    # 验证写入的内容
    yaml_data = yaml.safe_load((saved_path / "template.yaml").read_text(encoding="utf-8"))
    assert yaml_data["name"] == "custom"
    assert (saved_path / "style.css").read_text(encoding="utf-8") == css


def test_resolve_template_cli_override() -> None:
    """CLI 参数优先级最高"""
    from aap.core.models import Article, ArticleMeta

    manager = TemplateManager()
    article = Article(meta=ArticleMeta(template="minimal"), content_html="")

    config = manager.resolve_template(article, cli_override="minimal")
    assert config.name == "minimal"


def test_resolve_template_front_matter() -> None:
    """Front Matter 模板优先级高于默认"""
    from aap.core.models import Article, ArticleMeta

    manager = TemplateManager(default_template="minimal")
    article = Article(meta=ArticleMeta(template="minimal"), content_html="")

    config = manager.resolve_template(article)
    assert config.name == "minimal"


def test_resolve_template_fallback_to_default() -> None:
    """模板不存在时回退到默认模板"""
    from aap.core.models import Article, ArticleMeta

    manager = TemplateManager(default_template="minimal")
    article = Article(meta=ArticleMeta(template="nonexistent"), content_html="")

    config = manager.resolve_template(article)
    assert config.name == "minimal"


def test_resolve_template_name() -> None:
    """resolve_template_name 不加载配置,只返回名称"""
    from aap.core.models import Article, ArticleMeta

    manager = TemplateManager()
    article = Article(meta=ArticleMeta(template="my-tpl"), content_html="")
    assert manager.resolve_template_name(article) == "my-tpl"
    assert manager.resolve_template_name(article, cli_override="cli-tpl") == "cli-tpl"


def test_template_priority_project_over_builtin(tmp_path: Path) -> None:
    """项目模板覆盖内置模板"""
    project_dir = tmp_path / "project_templates"
    project_minimal = project_dir / "minimal"
    project_minimal.mkdir(parents=True)
    (project_minimal / "template.yaml").write_text(
        "name: minimal\ndescription: 项目自定义\n", encoding="utf-8"
    )
    (project_minimal / "style.css").write_text("section { color: blue; }", encoding="utf-8")

    manager = TemplateManager(project_templates_dir=project_dir)
    config = manager.load_template("minimal")
    assert config.description == "项目自定义"

    css = manager.load_template_css("minimal")
    assert "blue" in css
