"""图片绑定器

交互式将图片清单与微信 media_id / URL 绑定。

应用场景:
- 手动导出路径(aap export)后,用户已将图片上传到微信素材库
- 通过本工具逐张输入 media_id 与 URL,自动回填到 manifest.json
- 同时生成替换好图片 URL 的 article_final.html

使用方式:
    binder = ImageBinder()
    binder.bind(Path("manifest.json"))
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from aap.core.html_utils import replace_image_src


class ImageBinder:
    """图片绑定器

    交互式将图片清单与微信 media_id 绑定,
    用于手动导出路径中已上传图片的回填。
    """

    def __init__(self, input_func=None) -> None:
        """初始化绑定器

        Args:
            input_func: 输入函数(默认 input,便于测试时注入)
        """
        self._input = input_func or input

    def bind(
        self,
        manifest_path: Path,
        html_path: Optional[Path] = None,
        output_html_name: str = "article_final.html",
    ) -> Path:
        """交互式绑定图片 media_id 与 URL

        Args:
            manifest_path: 图片清单文件路径(manifest.json)
            html_path: 待替换的 HTML 文件路径(默认与 manifest 同目录的 article.html)
            output_html_name: 替换后的 HTML 文件名

        Returns:
            替换后的 HTML 文件路径

        Raises:
            FileNotFoundError: manifest 或 HTML 文件不存在
            ValueError: manifest 格式错误
        """
        manifest_path = Path(manifest_path)
        if not manifest_path.exists():
            raise FileNotFoundError(f"清单文件不存在: {manifest_path}")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"清单 JSON 解析失败: {e}") from e

        if not isinstance(manifest, dict) or "images" not in manifest:
            raise ValueError("清单格式错误: 缺少 images 字段")

        # 确定待替换的 HTML 文件
        if html_path is None:
            html_path = manifest_path.parent / "article.html"
        html_path = Path(html_path)
        if not html_path.exists():
            raise FileNotFoundError(f"HTML 文件不存在: {html_path}")

        images = manifest.get("images", [])
        if not images:
            print("清单中没有图片需要绑定")
            return html_path

        # 逐张交互式输入
        print("=" * 60)
        print("AAP 图片绑定 - 请逐张输入微信图片 URL")
        print("=" * 60)
        print(f"共 {len(images)} 张图片需要绑定")
        print("提示: 直接回车跳过当前图片(保留占位符)")
        print("     输入 q 退出(已绑定的会保存)")
        print("")

        # 构建 {占位符: URL} 映射
        mapping: dict[str, str] = {}
        bound_count = 0

        for i, img in enumerate(images, start=1):
            idx = img.get("index", i)
            placeholder = img.get("placeholder", f"{{{{IMG_{idx:02d}}}}}")
            packed_name = img.get("packed_name", "")
            alt = img.get("alt", "")
            existing_url = img.get("wechat_url", "")
            existing_id = img.get("wechat_media_id", "")

            print(f"[{i}/{len(images)}] {packed_name or placeholder}")
            if alt:
                print(f"  描述: {alt}")
            if existing_url:
                print(f"  当前 URL: {existing_url}")

            # 输入 URL
            url = self._input("  微信图片 URL: ").strip()
            if url.lower() == "q":
                print("用户中断绑定")
                break
            if not url:
                # 跳过(保留占位符)
                print("  跳过\n")
                continue

            # 输入 media_id(可选,正文图片不需要,但封面需要)
            media_id = self._input("  media_id(可留空): ").strip()
            if media_id.lower() == "q":
                break

            img["wechat_url"] = url
            if media_id:
                img["wechat_media_id"] = media_id
            mapping[placeholder] = url
            bound_count += 1
            print(f"  已绑定: {url}\n")

        # 写回 manifest
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"清单已更新: {manifest_path}")
        print(f"本次绑定 {bound_count} 张图片")

        if not mapping:
            return html_path

        # 替换 HTML 中的占位符
        html = html_path.read_text(encoding="utf-8")
        final_html = replace_image_src(html, mapping)
        # 也替换 src 之外的文本占位符(如 <img src="{{IMG_01}}"> 已由上面处理)
        # 这里再保险替换一次(防止 src 已是占位符字符串)
        for placeholder, url in mapping.items():
            final_html = final_html.replace(placeholder, url)

        output_path = html_path.parent / output_html_name
        output_path.write_text(final_html, encoding="utf-8")
        print(f"最终 HTML 已生成: {output_path}")

        return output_path

    def bind_non_interactive(
        self,
        manifest_path: Path,
        bindings: dict[str, str],
        html_path: Optional[Path] = None,
        output_html_name: str = "article_final.html",
    ) -> Path:
        """非交互式绑定(批量传入 {占位符: URL})

        便于脚本化场景或测试。

        Args:
            manifest_path: 清单文件路径
            bindings: {placeholder: url} 映射
            html_path: 待替换的 HTML 文件路径
            output_html_name: 替换后的 HTML 文件名

        Returns:
            替换后的 HTML 文件路径
        """
        manifest_path = Path(manifest_path)
        if not manifest_path.exists():
            raise FileNotFoundError(f"清单文件不存在: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or "images" not in manifest:
            raise ValueError("清单格式错误: 缺少 images 字段")

        if html_path is None:
            html_path = manifest_path.parent / "article.html"
        html_path = Path(html_path)
        if not html_path.exists():
            raise FileNotFoundError(f"HTML 文件不存在: {html_path}")

        # 更新 manifest
        for img in manifest.get("images", []):
            placeholder = img.get("placeholder", "")
            if placeholder in bindings:
                img["wechat_url"] = bindings[placeholder]
                # 若 URL 中包含 media_id(如 mmbiz.qpic.cn/.../xxx),尝试提取
                # 这里不强制要求 media_id

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 替换 HTML
        html = html_path.read_text(encoding="utf-8")
        final_html = replace_image_src(html, bindings)
        for placeholder, url in bindings.items():
            final_html = final_html.replace(placeholder, url)

        output_path = html_path.parent / output_html_name
        output_path.write_text(final_html, encoding="utf-8")
        return output_path
