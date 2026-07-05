"""图片打包器

将文章引用的图片打包到输出目录:
1. 按出现顺序重命名为 01.png、02.png(避免中文名/冲突)
2. 复制到 images/ 子目录
3. 生成 manifest.json(记录原路径、新名、占位符、media_id 待填)
4. (可选)将整个输出目录打包为 ZIP

输出目录结构示例:
    output/
    ├── article.html
    ├── images/
    │   ├── 01.png
    │   └── 02.png
    ├── manifest.json
    └── INSTRUCTIONS.txt
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from aap.core.models import ImageRef


class ImagePacker:
    """图片打包器

    将文章引用的图片打包到输出目录,并生成清单文件。
    """

    def pack(
        self,
        images: list[ImageRef],
        output_dir: Path,
        skip_missing: bool = True,
    ) -> Path:
        """打包图片到输出目录

        Args:
            images: 图片引用列表
            output_dir: 输出目录
            skip_missing: 是否跳过缺失文件(若 False,缺失则报错)

        Returns:
            images 子目录路径

        Raises:
            FileNotFoundError: skip_missing=False 且图片文件不存在
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        for img in images:
            src_path = Path(img.original_path)
            if not src_path.exists():
                if skip_missing:
                    continue
                raise FileNotFoundError(f"图片文件不存在: {src_path}")

            # 按索引重命名为 01.<ext>
            ext = src_path.suffix or ".png"
            new_name = f"{img.index:02d}{ext}"
            dst_path = images_dir / new_name
            shutil.copy2(src_path, dst_path)

            # 回填 packed_name,供后续流程使用
            img.packed_name = new_name

        return images_dir

    def generate_manifest(
        self,
        images: list[ImageRef],
        article_path: Path,
        extra: Optional[dict] = None,
    ) -> dict:
        """生成图片清单字典

        Args:
            images: 图片引用列表
            article_path: 文章路径
            extra: 额外字段(如 template、title)

        Returns:
            清单字典(可序列化为 manifest.json)
        """
        return {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "article_path": str(article_path),
            "article_title": extra.get("title", "") if extra else "",
            "template": extra.get("template", "") if extra else "",
            "image_count": len(images),
            "images": [
                {
                    "index": img.index,
                    "original_path": img.original_path,
                    "alt": img.alt,
                    "packed_name": img.packed_name,
                    "placeholder": img.placeholder,
                    "wechat_media_id": "",  # 待用户填入
                    "wechat_url": "",       # 待用户填入
                }
                for img in images
            ],
        }

    def write_manifest(
        self,
        manifest: dict,
        output_dir: Path,
        filename: str = "manifest.json",
    ) -> Path:
        """将清单写入 manifest.json

        Args:
            manifest: 清单字典
            output_dir: 输出目录
            filename: 文件名

        Returns:
            清单文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / filename
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    def write_instructions(
        self,
        images: list[ImageRef],
        output_dir: Path,
        article_title: str = "",
    ) -> Path:
        """生成 INSTRUCTIONS.txt(给使用者的操作指引)

        Args:
            images: 图片引用列表
            output_dir: 输出目录
            article_title: 文章标题(用于显示)

        Returns:
            指引文件路径
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "INSTRUCTIONS.txt"

        lines: list[str] = [
            "=" * 60,
            "AAP 手动导出包 - 操作指南",
            "=" * 60,
            "",
            f"文章标题: {article_title or '(未指定)'}",
            f"图片数量: {len(images)}",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "-" * 60,
            "步骤 1:上传图片到微信公众号素材库",
            "-" * 60,
            "",
            "登录微信公众平台 https://mp.weixin.qq.com",
            "进入:素材管理 → 图片素材 → 上传",
            "",
            "上传 images/ 目录下的所有图片(01.png, 02.png, ...)",
            "上传后,每张图片会显示一个 URL(以 mmbiz.qpic.cn 开头)",
            "记下每个 URL,按顺序填入 manifest.json 的 wechat_url 字段",
            "",
            "图片清单:",
        ]
        for img in images:
            lines.append(f"  [{img.index:02d}] {img.packed_name or '(未打包)'}")
            lines.append(f"       占位符: {img.placeholder}")
            lines.append(f"       原路径: {img.original_path}")
            if img.alt:
                lines.append(f"       描述:   {img.alt}")
            lines.append("")

        lines.extend([
            "-" * 60,
            "步骤 2:替换 HTML 中的图片占位符",
            "-" * 60,
            "",
            "打开 article.html,搜索占位符(如 {{IMG_01}})",
            "用步骤 1 获得的微信图片 URL 替换占位符",
            "",
            "也可以使用 aap 命令行辅助:",
            "  aap image bind manifest.json",
            "(会交互式引导你输入每个 media_id/URL,自动替换)",
            "",
            "-" * 60,
            "步骤 3:复制 HTML 到微信公众号编辑器",
            "-" * 60,
            "",
            "用浏览器打开 article.html,全选(Ctrl+A),复制(Ctrl+C)",
            "粘贴到微信公众号编辑器(Ctrl+V)",
            "检查排版是否正确,微调样式后保存草稿",
            "",
            "提示: 微信编辑器会自动应用内联样式,排版应与本地预览一致",
            "若发现样式异常,可使用 'aap preview article.md' 本地预览调试",
            "",
            "=" * 60,
        ])

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def zip_output(self, output_dir: Path, zip_path: Optional[Path] = None) -> Path:
        """将输出目录打包为 ZIP

        Args:
            output_dir: 输出目录
            zip_path: ZIP 文件路径(默认 output_dir 同级同名 .zip)

        Returns:
            ZIP 文件路径
        """
        output_dir = Path(output_dir)
        if zip_path is None:
            zip_path = output_dir.with_suffix(".zip")
        zip_path = Path(zip_path)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in output_dir.rglob("*"):
                if file.is_file():
                    arcname = file.relative_to(output_dir)
                    zf.write(file, arcname)
        return zip_path
