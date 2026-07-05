"""ArticleParser 测试"""
from pathlib import Path

from aap.core.parser import ArticleParser


def test_parse_basic(sample_md_path: Path) -> None:
    """测试基础解析功能:Front Matter、正文渲染、图片扫描"""
    parser = ArticleParser()
    article = parser.parse(sample_md_path)

    # 元信息
    assert article.meta.title == "测试文章"
    assert article.meta.author == "AAP"
    assert article.meta.summary == "用于测试的示例文章"
    assert article.meta.template == "minimal"
    assert article.meta.tags == ["测试", "示例"]

    # 正文 HTML
    assert "<h1>测试文章标题</h1>" in article.content_html
    assert "<h2>二级标题</h2>" in article.content_html
    assert "<strong>加粗</strong>" in article.content_html
    assert "<em>斜体</em>" in article.content_html
    assert '<a href="https://example.com">链接</a>' in article.content_html
    assert "<table>" in article.content_html
    assert "<blockquote>" in article.content_html
    assert "<ul>" in article.content_html
    assert "<pre><code" in article.content_html

    # 图片
    assert len(article.images) == 1
    img = article.images[0]
    assert img.index == 1
    assert img.alt == "示例图片"
    assert img.placeholder == "{{IMG_01}}"
    # 原始路径已解析为绝对路径
    assert Path(img.original_path).is_absolute()
    assert img.original_path.endswith("sample.png")


def test_parse_title_fallback_from_first_heading(tmp_path: Path) -> None:
    """Front Matter 未指定 title 时,从正文第一个标题提取"""
    md = tmp_path / "no_title.md"
    md.write_text(
        "---\nauthor: tester\n---\n\n# 自动提取的标题\n\n正文内容",
        encoding="utf-8",
    )
    parser = ArticleParser()
    article = parser.parse(md)
    assert article.meta.title == "自动提取的标题"


def test_parse_title_fallback_to_filename(tmp_path: Path) -> None:
    """无 Front Matter 也无标题时,使用文件名作为 title"""
    md = tmp_path / "filename_default.md"
    md.write_text("只有正文,没有标题", encoding="utf-8")
    parser = ArticleParser()
    article = parser.parse(md)
    assert article.meta.title == "filename_default"


def test_parse_skips_remote_images(tmp_path: Path) -> None:
    """远程图片 URL 不进入 ImageRef 列表"""
    md = tmp_path / "remote_img.md"
    md.write_text(
        "![本地](local.png)\n![远程](https://example.com/remote.png)",
        encoding="utf-8",
    )
    parser = ArticleParser()
    article = parser.parse(md)
    # 只有 local.png 进入列表
    assert len(article.images) == 1
    assert "local.png" in article.images[0].original_path


def test_parse_dedup_same_image(tmp_path: Path) -> None:
    """同一图片多次引用只算一张"""
    md = tmp_path / "dup.md"
    md.write_text(
        "![img](a.png)\n\n中间内容\n\n![img again](a.png)",
        encoding="utf-8",
    )
    parser = ArticleParser()
    article = parser.parse(md)
    assert len(article.images) == 1


def test_parse_tags_string(tmp_path: Path) -> None:
    """tags 支持逗号分隔字符串"""
    md = tmp_path / "tags_str.md"
    md.write_text(
        "---\ntags: alpha, beta, gamma\n---\n\n正文",
        encoding="utf-8",
    )
    parser = ArticleParser()
    article = parser.parse(md)
    assert article.meta.tags == ["alpha", "beta", "gamma"]


def test_parse_file_not_found() -> None:
    """文件不存在时抛出 FileNotFoundError"""
    import pytest

    parser = ArticleParser()
    with pytest.raises(FileNotFoundError):
        parser.parse(Path("nonexistent.md"))
