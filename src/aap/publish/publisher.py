"""文章发布器

执行完整的 API 发布流程(对应需求 FR-6):
1. 解析 Markdown (parser)
2. 解析模板 (template_manager)
3. 渲染 HTML (renderer)
4. 上传正文图片 (material.upload_content_image) → 替换 URL
5. 上传封面图 (material.upload_thumb) → thumb_media_id
6. 上传草稿 (draft.add_draft) → 草稿 media_id
7. 记录历史
8. 输出结果与指引

输出目录(本地留存): <output_dir>/<md_stem>_<timestamp>/
- article.html          (已替换图片 URL 的最终 HTML)
- manifest.json         (图片上传记录)
- publish_log.json      (发布日志)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from aap.config.manager import ConfigManager
from aap.core.models import AppConfig, Article, ImageRef, PublishResult, TemplateConfig
from aap.core.parser import ArticleParser
from aap.core.renderer import HTMLRenderer
from aap.image.scanner import ImageScanner
from aap.templates.manager import TemplateManager
from aap.utils.path import get_history_path
from aap.wechat.client import WeChatClient


class Publisher:
    """文章发布器

    执行完整的 API 发布流程:
    解析 Markdown → 渲染 HTML → 上传图片 → 新增草稿。
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        parser: Optional[ArticleParser] = None,
        renderer: Optional[HTMLRenderer] = None,
        template_manager: Optional[TemplateManager] = None,
        scanner: Optional[ImageScanner] = None,
    ) -> None:
        """初始化发布器

        Args:
            config: 应用配置(为空则从 ConfigManager 加载)
            parser: 文章解析器
            renderer: HTML 渲染器
            template_manager: 模板管理器
            scanner: 图片扫描器
        """
        self.config = config if config is not None else ConfigManager().load()
        self.parser = parser or ArticleParser()
        self.renderer = renderer or HTMLRenderer()
        # 模板管理器使用配置中的 default_template
        self.template_manager = template_manager or TemplateManager(
            default_template=self.config.default_template
        )
        self.scanner = scanner or ImageScanner()

    async def publish(
        self, md_path: Path, cli_template: Optional[str] = None
    ) -> PublishResult:
        """发布 Markdown 文章到微信公众号草稿箱

        Args:
            md_path: Markdown 文件路径
            cli_template: 命令行指定的模板名(覆盖 Front Matter)

        Returns:
            发布结果对象
        """
        md_path = Path(md_path).resolve()
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown 文件不存在: {md_path}")

        # 1. 解析文章
        article = self.parser.parse(md_path)
        title = article.meta.title or md_path.stem

        # 2. 解析模板
        template_name = self.template_manager.resolve_template_name(article, cli_template)
        try:
            template = self.template_manager.load_template(template_name)
            css = self.template_manager.load_template_css(template_name)
        except FileNotFoundError:
            template = self.template_manager.load_template(self.config.default_template)
            css = self.template_manager.load_template_css(self.config.default_template)
            template_name = self.config.default_template

        # 3. 创建 WeChatClient(用于上传)
        async with WeChatClient(self.config) as client:
            # 4. 上传正文图片
            images = self.scanner.scan(article)
            existing, missing = self.scanner.check_exists(images)
            if missing:
                # 警告但不中断,缺失图片保留占位符
                pass

            if existing:
                await self._upload_content_images(existing, client)

            # 5. 渲染最终 HTML(图片用微信 URL)
            html = self.renderer.render_for_publish(article, template, css=css)

            # 6. 上传封面图
            thumb_media_id = ""
            if article.meta.cover:
                cover_path = self._resolve_cover_path(article.meta.cover, md_path)
                if cover_path and cover_path.exists():
                    try:
                        thumb_media_id = await client.material.upload_thumb(cover_path)
                    except RuntimeError as e:
                        # 封面上传失败属于致命错误(微信草稿必须有 thumb_media_id)
                        return PublishResult(
                            success=False,
                            error=f"封面上传失败: {e}",
                            article_title=title,
                        )
                else:
                    return PublishResult(
                        success=False,
                        error=f"封面图不存在: {article.meta.cover}",
                        article_title=title,
                    )
            else:
                return PublishResult(
                    success=False,
                    error="Front Matter 未指定 cover(封面图)",
                    article_title=title,
                )

            # 7. 上传草稿
            digest = article.meta.summary or self._extract_digest(article)
            article_data = {
                "title": title,
                "author": article.meta.author or self.config.account.nickname or "",
                "digest": digest,
                "content": html,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
            }
            if article.meta.category:
                article_data["content_source_url"] = ""

            try:
                draft_media_id = await client.draft.add_draft(article_data)
            except (RuntimeError, ValueError) as e:
                return PublishResult(
                    success=False,
                    error=f"草稿上传失败: {e}",
                    article_title=title,
                    thumb_media_id=thumb_media_id,
                    image_count=len(existing),
                )

        # 8. 写本地留存文件
        output_dir = self._make_output_dir(md_path)
        self._write_outputs(
            output_dir=output_dir,
            html=html,
            article=article,
            md_path=md_path,
            template_name=template_name,
            draft_media_id=draft_media_id,
            thumb_media_id=thumb_media_id,
        )

        # 9. 记录历史
        self._record_history(
            md_path=md_path,
            title=title,
            draft_media_id=draft_media_id,
            thumb_media_id=thumb_media_id,
            image_count=len(existing),
            template_name=template_name,
        )

        return PublishResult(
            success=True,
            draft_media_id=draft_media_id,
            thumb_media_id=thumb_media_id,
            image_count=len(existing),
            article_title=title,
        )

    async def _upload_content_images(
        self, images: list[ImageRef], client: WeChatClient
    ) -> None:
        """并发上传正文图片到微信,回填 wechat_url

        限制 3 并发,失败重试 3 次(指数退避)。
        """
        sem = asyncio.Semaphore(3)

        async def _upload_one(img: ImageRef) -> None:
            async with sem:
                path = Path(img.original_path)
                if not path.exists():
                    return
                # 重试 3 次
                for attempt in range(3):
                    try:
                        url = await client.material.upload_content_image(path)
                        img.wechat_url = url
                        return
                    except RuntimeError as e:
                        if attempt == 2:
                            # 最后一次失败,保留占位符
                            break
                        await asyncio.sleep(2 ** attempt)

        await asyncio.gather(*[_upload_one(img) for img in images])

    def _resolve_cover_path(self, cover: str, md_path: Path) -> Optional[Path]:
        """解析封面图路径(支持相对路径与绝对路径)"""
        cover_p = Path(cover)
        if cover_p.is_absolute():
            return cover_p if cover_p.exists() else None
        # 相对于 md 所在目录
        resolved = (md_path.parent / cover_p).resolve()
        return resolved if resolved.exists() else None

    def _extract_digest(self, article: Article) -> str:
        """从正文提取摘要(取前 54 字符的纯文本)"""
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(article.content_html, "lxml")
            text = soup.get_text(separator=" ", strip=True)
        except Exception:
            text = article.content_html
        text = text.replace("\n", " ").strip()
        return text[:54] + ("..." if len(text) > 54 else "")

    def _make_output_dir(self, md_path: Path) -> Path:
        """创建本次发布的输出目录"""
        output_root = Path(self.config.publish.output_dir or ".aap/output")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = output_root / f"{md_path.stem}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _write_outputs(
        self,
        output_dir: Path,
        html: str,
        article: Article,
        md_path: Path,
        template_name: str,
        draft_media_id: str,
        thumb_media_id: str,
    ) -> None:
        """写入本地留存文件:article.html、manifest.json、publish_log.json"""
        # article.html
        (output_dir / "article.html").write_text(html, encoding="utf-8")

        # manifest.json
        manifest = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "article_path": str(md_path),
            "article_title": article.meta.title,
            "template": template_name,
            "image_count": len(article.images),
            "images": [
                {
                    "index": img.index,
                    "original_path": img.original_path,
                    "alt": img.alt,
                    "placeholder": img.placeholder,
                    "wechat_url": img.wechat_url,
                    "wechat_media_id": img.wechat_media_id,
                }
                for img in article.images
            ],
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # publish_log.json
        log = {
            "publish_time": datetime.now().isoformat(timespec="seconds"),
            "article_path": str(md_path),
            "title": article.meta.title,
            "draft_media_id": draft_media_id,
            "thumb_media_id": thumb_media_id,
            "image_count": len(article.images),
            "template": template_name,
            "scf_used": self.config.scf.enabled,
        }
        (output_dir / "publish_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _record_history(
        self,
        md_path: Path,
        title: str,
        draft_media_id: str,
        thumb_media_id: str,
        image_count: int,
        template_name: str,
    ) -> None:
        """追加发布历史到 ~/.aap/history.jsonl"""
        if not self.config.history.enabled:
            return
        try:
            history_path = get_history_path(self.config.history.file or None)
            history_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "publish_time": datetime.now().isoformat(timespec="seconds"),
                "article_path": str(md_path),
                "title": title,
                "draft_media_id": draft_media_id,
                "thumb_media_id": thumb_media_id,
                "image_count": image_count,
                "template": template_name,
                "scf_used": self.config.scf.enabled,
            }
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # 历史记录失败不影响发布结果
            pass
