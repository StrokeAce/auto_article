"""ImageBinder 测试"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aap.image.binder import ImageBinder


@pytest.fixture
def sample_manifest(tmp_path: Path) -> Path:
    """生成示例 manifest.json 与 article.html"""
    manifest_data = {
        "version": "1.0",
        "article_title": "测试文章",
        "image_count": 2,
        "images": [
            {
                "index": 1,
                "original_path": "/img/01.png",
                "alt": "图一",
                "packed_name": "01.png",
                "placeholder": "{{IMG_01}}",
                "wechat_media_id": "",
                "wechat_url": "",
            },
            {
                "index": 2,
                "original_path": "/img/02.png",
                "alt": "图二",
                "packed_name": "02.png",
                "placeholder": "{{IMG_02}}",
                "wechat_media_id": "",
                "wechat_url": "",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    html = (
        '<section><img src="{{IMG_01}}" alt="图一">'
        '<img src="{{IMG_02}}" alt="图二"></section>'
    )
    (tmp_path / "article.html").write_text(html, encoding="utf-8")
    return manifest_path


# ===== bind_non_interactive 测试 =====


def test_bind_non_interactive_basic(sample_manifest: Path) -> None:
    """非交互式绑定替换占位符"""
    binder = ImageBinder()
    bindings = {
        "{{IMG_01}}": "https://mmbiz.qpic.cn/01.png",
        "{{IMG_02}}": "https://mmbiz.qpic.cn/02.png",
    }
    output = binder.bind_non_interactive(sample_manifest, bindings)

    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "{{IMG_01}}" not in html
    assert "{{IMG_02}}" not in html
    assert "https://mmbiz.qpic.cn/01.png" in html
    assert "https://mmbiz.qpic.cn/02.png" in html


def test_bind_non_interactive_updates_manifest(sample_manifest: Path) -> None:
    """绑定后 manifest 的 wechat_url 字段被更新"""
    binder = ImageBinder()
    bindings = {"{{IMG_01}}": "https://x.example.com/1.png"}
    binder.bind_non_interactive(sample_manifest, bindings)

    manifest = json.loads(sample_manifest.read_text(encoding="utf-8"))
    images = manifest["images"]
    assert images[0]["wechat_url"] == "https://x.example.com/1.png"
    # 未绑定的图片 URL 仍为空
    assert images[1]["wechat_url"] == ""


def test_bind_non_interactive_partial_bindings(sample_manifest: Path) -> None:
    """部分绑定只替换提供的占位符"""
    binder = ImageBinder()
    bindings = {"{{IMG_01}}": "https://x.example.com/1.png"}
    output = binder.bind_non_interactive(sample_manifest, bindings)

    html = output.read_text(encoding="utf-8")
    assert "https://x.example.com/1.png" in html
    # 未提供的占位符保留
    assert "{{IMG_02}}" in html


def test_bind_non_interactive_custom_output_name(sample_manifest: Path) -> None:
    """自定义输出文件名"""
    binder = ImageBinder()
    output = binder.bind_non_interactive(
        sample_manifest,
        {"{{IMG_01}}": "u1"},
        output_html_name="final.html",
    )
    assert output.name == "final.html"
    assert output.exists()


def test_bind_non_interactive_missing_manifest(tmp_path: Path) -> None:
    """manifest 不存在抛 FileNotFoundError"""
    binder = ImageBinder()
    with pytest.raises(FileNotFoundError, match="清单文件不存在"):
        binder.bind_non_interactive(tmp_path / "no.json", {})


def test_bind_non_interactive_missing_html(tmp_path: Path) -> None:
    """HTML 文件不存在抛 FileNotFoundError"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"images": [{"placeholder": "{{IMG_01}}"}]}),
        encoding="utf-8",
    )
    binder = ImageBinder()
    with pytest.raises(FileNotFoundError, match="HTML 文件不存在"):
        binder.bind_non_interactive(manifest_path, {"{{IMG_01}}": "u"})


def test_bind_non_interactive_invalid_manifest(tmp_path: Path) -> None:
    """manifest 格式错误(无 images 字段)抛 ValueError"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    (tmp_path / "article.html").write_text("<p>x</p>", encoding="utf-8")
    binder = ImageBinder()
    with pytest.raises(ValueError, match="缺少 images 字段"):
        binder.bind_non_interactive(manifest_path, {})


def test_bind_non_interactive_invalid_json(tmp_path: Path) -> None:
    """manifest 非法 JSON 抛异常"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("not json{", encoding="utf-8")
    (tmp_path / "article.html").write_text("<p>x</p>", encoding="utf-8")
    binder = ImageBinder()
    with pytest.raises((ValueError, json.JSONDecodeError)):
        binder.bind_non_interactive(manifest_path, {})


# ===== bind (交互式) 测试 =====


def test_bind_interactive_with_mock_input(sample_manifest: Path) -> None:
    """交互式绑定(注入 input_func)"""
    inputs = iter([
        "https://mmbiz.qpic.cn/01.png",  # 第一张 URL
        "media-001",                      # 第一张 media_id
        "https://mmbiz.qpic.cn/02.png",  # 第二张 URL
        "",                                # 第二张 media_id 留空
    ])
    binder = ImageBinder(input_func=lambda _: next(inputs))

    output = binder.bind(sample_manifest)
    html = output.read_text(encoding="utf-8")
    assert "https://mmbiz.qpic.cn/01.png" in html
    assert "https://mmbiz.qpic.cn/02.png" in html

    # manifest 也应被更新
    manifest = json.loads(sample_manifest.read_text(encoding="utf-8"))
    assert manifest["images"][0]["wechat_url"] == "https://mmbiz.qpic.cn/01.png"
    assert manifest["images"][0]["wechat_media_id"] == "media-001"


def test_bind_interactive_skip(sample_manifest: Path) -> None:
    """交互式绑定中跳过(回车)保留占位符"""
    inputs = iter([
        "",  # 跳过第一张
        "https://mmbiz.qpic.cn/02.png",
        "",
    ])
    binder = ImageBinder(input_func=lambda _: next(inputs))
    output = binder.bind(sample_manifest)
    html = output.read_text(encoding="utf-8")
    # 第一张保留占位符
    assert "{{IMG_01}}" in html
    # 第二张已替换
    assert "https://mmbiz.qpic.cn/02.png" in html


def test_bind_interactive_quit(sample_manifest: Path) -> None:
    """交互式绑定中输入 q 退出"""
    inputs = iter(["q"])
    binder = ImageBinder(input_func=lambda _: next(inputs))
    output = binder.bind(sample_manifest)
    # 退出后仍返回 HTML 路径,占位符未替换
    html = output.read_text(encoding="utf-8")
    assert "{{IMG_01}}" in html


def test_bind_interactive_missing_manifest(tmp_path: Path) -> None:
    """交互式绑定 manifest 不存在抛 FileNotFoundError"""
    binder = ImageBinder(input_func=lambda _: "")
    with pytest.raises(FileNotFoundError):
        binder.bind(tmp_path / "no.json")


def test_bind_interactive_empty_images(tmp_path: Path) -> None:
    """无图片时直接返回 HTML 路径"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"images": []}), encoding="utf-8"
    )
    (tmp_path / "article.html").write_text("<p>x</p>", encoding="utf-8")
    binder = ImageBinder(input_func=lambda _: "")
    output = binder.bind(manifest_path)
    # 无图片时返回原 HTML 路径
    assert output.name == "article.html"
