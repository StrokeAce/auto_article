"""html_utils 工具函数测试"""
from aap.core.html_utils import (
    extract_images,
    filter_unsupported_tags,
    inline_css,
    replace_image_src,
    wrap_section,
)


def test_inline_css_basic() -> None:
    """CSS 规则内联到对应标签的 style 属性"""
    html = "<p>hello</p><h1>title</h1>"
    css = "p { color: red; font-size: 14px } h1 { color: blue }"
    result = inline_css(html, css)
    assert 'style="color: red; font-size: 14px"' in result
    assert 'style="color: blue"' in result


def test_inline_css_preserves_existing_style() -> None:
    """已有 style 属性与 CSS 合并,CSS 优先"""
    html = '<p style="margin: 10px">hello</p>'
    css = "p { color: red }"
    result = inline_css(html, css)
    assert "color: red" in result
    assert "margin: 10px" in result


def test_inline_css_empty() -> None:
    """空 CSS 不修改 HTML"""
    html = "<p>hello</p>"
    assert inline_css(html, "") == html
    assert inline_css(html, "   ") == html


def test_inline_css_compound_selector() -> None:
    """复合选择器(逗号分隔)"""
    html = "<h1>a</h1><h2>b</h2>"
    css = "h1, h2 { color: red }"
    result = inline_css(html, css)
    assert result.count("color: red") == 2


def test_filter_unsupported_tags_removes_script() -> None:
    """script 标签连同内容一起删除"""
    html = "<p>good</p><script>bad()</script><p>end</p>"
    result = filter_unsupported_tags(html)
    assert "bad()" not in result
    assert "<script" not in result
    assert "good" in result
    assert "end" in result


def test_filter_unsupported_tags_removes_style() -> None:
    """style 标签删除(微信编辑器会过滤掉)"""
    html = "<p>x</p><style>p { color: red }</style>"
    result = filter_unsupported_tags(html)
    assert "<style" not in result
    assert "color: red" not in result


def test_filter_unsupported_tags_removes_iframe() -> None:
    """iframe 标签删除"""
    html = '<p>x</p><iframe src="evil.com"></iframe>'
    result = filter_unsupported_tags(html)
    assert "<iframe" not in result
    assert "evil.com" not in result


def test_filter_unsupported_tags_unwraps_unknown() -> None:
    """未知标签 unwrap(保留子内容)"""
    html = "<div><custom>内容</custom></div>"
    result = filter_unsupported_tags(html)
    assert "<custom" not in result
    assert "内容" in result


def test_filter_unsupported_tags_removes_comments() -> None:
    """HTML 注释删除"""
    html = "<p>a</p><!-- comment --><p>b</p>"
    result = filter_unsupported_tags(html)
    assert "<!--" not in result
    assert "comment" not in result


def test_filter_unsupported_tags_strips_disallowed_attrs() -> None:
    """不允许的属性被移除"""
    html = '<p onclick="evil()" class="ok">x</p>'
    result = filter_unsupported_tags(html)
    assert "onclick" not in result
    assert 'class="ok"' in result


def test_extract_images_basic() -> None:
    """提取所有 img src,按顺序"""
    html = '<img src="a.png"><img src="b.png"><img src="a.png">'
    result = extract_images(html)
    # 去重
    assert result == ["a.png", "b.png"]


def test_extract_images_empty() -> None:
    """无图片返回空列表"""
    assert extract_images("<p>no img</p>") == []


def test_extract_images_supports_data_src() -> None:
    """支持 data-src 属性"""
    html = '<img data-src="x.png">'
    result = extract_images(html)
    assert result == ["x.png"]


def test_replace_image_src() -> None:
    """替换图片 src"""
    html = '<img src="a.png"><img src="b.png">'
    result = replace_image_src(html, {"a.png": "new_a.png"})
    assert 'src="new_a.png"' in result
    assert 'src="b.png"' in result
    assert "a.png" not in result.replace("new_a.png", "")


def test_replace_image_src_empty_mapping() -> None:
    """空映射不修改 HTML"""
    html = '<img src="a.png">'
    assert replace_image_src(html, {}) == html


def test_wrap_section_no_style() -> None:
    """无样式包裹 section"""
    result = wrap_section("<p>hi</p>")
    assert result.startswith("<section>")
    assert result.endswith("</section>")
    assert "<p>hi</p>" in result


def test_wrap_section_with_style() -> None:
    """带样式包裹 section"""
    result = wrap_section("<p>hi</p>", "color: red")
    assert '<section style="color: red">' in result


def test_full_pipeline_filter_then_inline() -> None:
    """完整流程:先过滤再内联 CSS"""
    html = "<p>good</p><script>bad()</script>"
    css = "p { color: red }"
    # 先过滤
    filtered = filter_unsupported_tags(html)
    assert "bad()" not in filtered
    # 再内联
    inlined = inline_css(filtered, css)
    assert 'style="color: red"' in inlined
    assert "<script" not in inlined
