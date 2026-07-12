"""本地预览服务

基于 FastAPI 提供文章渲染效果预览,支持:
- wechat 模式: 模拟微信编辑器外观(白底、内联样式)
- html 模式:   纯 HTML 预览(便于调试)
- 文件监听与热重载(WebSocket 推送)

两种启动方式:
1. 单文件模式: PreviewServer(md_path, mode="wechat", port=7788).start()
   只预览该 md 文件,访问 / 即可查看
2. 目录模式:   PreviewServer(dir_path, mode="wechat", port=7788).start()
   扫描目录下所有 .md 文件,首页 / 列出文章列表,/view/<name> 查看对应文章

URL 路由(目录模式):
- GET /                      文章列表页(目录模式) 或 文章预览页(单文件模式)
- GET /view/<md_stem>        渲染指定 md 文件(目录模式)
- GET /view/<md_stem>/raw    返回原始渲染 HTML(无外壳)
- GET /image/<path>          本地图片访问
- GET /icon/<filename>       模板章节图标(单图标模式)
- GET /icon/<sub_dir>/<idx>/<filename>  章节标题整图(整图模式)
- WS  /ws                    热重载(轮询当前查看的 md 文件 mtime)
"""
from __future__ import annotations

import asyncio
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse

from aap.core.models import Article
from aap.core.parser import ArticleParser
from aap.core.renderer import HTMLRenderer
from aap.templates.manager import TemplateManager


class PreviewServer:
    """本地预览服务

    基于 FastAPI + WebSocket 提供文章渲染效果预览与热重载,
    支持 wechat/html/screenshot 三种模式,以及单文件/目录两种启动方式。
    """

    def __init__(
        self,
        md_path: Path,
        mode: str = "wechat",
        port: int = 7788,
        open_browser: bool = True,
        template_name: Optional[str] = None,
    ) -> None:
        """初始化预览服务

        Args:
            md_path: Markdown 文件路径(单文件模式)或目录路径(目录模式)
            mode: 预览模式(wechat/html/screenshot)
            port: 监听端口
            open_browser: 是否自动打开浏览器
            template_name: 指定模板名(覆盖 Front Matter)
        """
        self.md_path = Path(md_path).resolve()
        self.is_dir_mode = self.md_path.is_dir()
        self.mode = mode
        self.port = port
        self.open_browser = open_browser
        self.template_name = template_name

        self.parser = ArticleParser()
        self.template_manager = TemplateManager()
        self.renderer = HTMLRenderer()

        self.app: Optional[FastAPI] = None
        # 当前正在查看的 md 文件(用于 WebSocket 热重载轮询)
        self._current_md: Path = self.md_path if not self.is_dir_mode else Path("")
        self._last_mtime: float = 0.0
        self._stop_event = threading.Event()

    def start(self) -> None:
        """启动预览服务(阻塞)"""
        self.app = self._build_app()

        if self.open_browser:
            url = f"http://127.0.0.1:{self.port}"
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()

        try:
            uvicorn.run(
                self.app,
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
            )
        finally:
            self._stop_event.set()

    # ===== 应用构建 =====

    def _build_app(self) -> FastAPI:
        """构建 FastAPI 应用"""
        app = FastAPI(title="AAP Preview", docs_url=None, redoc_url=None)
        clients: set[WebSocket] = set()

        @app.get("/", response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            """首页:目录模式返回文章列表,单文件模式返回文章预览"""
            if self.is_dir_mode:
                return HTMLResponse(self._render_list_page())
            return HTMLResponse(self._render_page(self.md_path))

        @app.get("/view/{md_stem}", response_class=HTMLResponse)
        async def view_article(md_stem: str) -> HTMLResponse:
            """目录模式:渲染指定 md 文件"""
            md_file = self._find_md_by_stem(md_stem)
            if md_file is None:
                return HTMLResponse(
                    f"<h1>未找到文章: {md_stem}</h1>"
                    f'<p><a href="/">返回列表</a></p>',
                    status_code=404,
                )
            # 更新当前查看的文件(用于 WebSocket 热重载)
            self._current_md = md_file
            return HTMLResponse(self._render_page(md_file))

        @app.get("/view/{md_stem}/raw", response_class=HTMLResponse)
        async def view_raw(md_stem: str) -> HTMLResponse:
            """目录模式:返回原始渲染 HTML"""
            md_file = self._find_md_by_stem(md_stem)
            if md_file is None:
                raise HTTPException(status_code=404, detail=f"未找到文章: {md_stem}")
            self._current_md = md_file
            return HTMLResponse(self._render_article_html(md_file))

        @app.get("/raw", response_class=HTMLResponse)
        async def raw() -> HTMLResponse:
            """单文件模式:返回原始渲染 HTML"""
            if self.is_dir_mode:
                return HTMLResponse(
                    '<p>目录模式请使用 /view/&lt;name&gt;/raw</p>',
                    status_code=400,
                )
            return HTMLResponse(self._render_article_html(self.md_path))

        @app.get("/image/{path:path}")
        async def serve_image(path: str):
            """提供本地图片访问"""
            # 目录模式:基于当前查看的 md 文件所在目录
            # 单文件模式:基于 md_path 所在目录
            base = self._current_md.parent.resolve() if self._current_md else self.md_path.parent
            if self.is_dir_mode and not self._current_md:
                base = self.md_path
            target = (base / path).resolve()
            try:
                target.relative_to(base)
            except ValueError:
                return HTMLResponse("Forbidden", status_code=403)
            if not target.exists() or not target.is_file():
                return HTMLResponse("Not Found", status_code=404)
            return FileResponse(target)

        @app.get("/icon/{filename}")
        async def serve_icon(filename: str):
            """提供模板章节装饰图标访问(单图标模式)"""
            cur_md = self._current_md or self.md_path
            if not cur_md.exists():
                return HTMLResponse("Not Found", status_code=404)
            article = self.parser.parse(cur_md)
            tpl_name = self.template_name or article.meta.template or "minimal"
            icon_path = self.template_manager.get_template_asset(tpl_name, filename)
            if icon_path and icon_path.exists():
                return FileResponse(icon_path)
            return HTMLResponse("Not Found", status_code=404)

        @app.get("/icon/{sub_dir}/{idx}/{filename}")
        async def serve_chapter_title_image(sub_dir: str, idx: str, filename: str):
            """提供章节标题整图访问(整图模式)"""
            cur_md = self._current_md or self.md_path
            if not cur_md.exists():
                return HTMLResponse("Not Found", status_code=404)
            article = self.parser.parse(cur_md)
            tpl_name = self.template_name or article.meta.template or "minimal"
            img_paths = self.template_manager.list_chapter_title_images(tpl_name, sub_dir)
            for p in img_paths:
                if p.name == filename:
                    return FileResponse(p)
            return HTMLResponse("Not Found", status_code=404)

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket 热重载端点

            轮询当前查看的 md 文件 mtime,变更则推送 reload。
            """
            await websocket.accept()
            clients.add(websocket)
            last_mtime = self._last_mtime
            try:
                while not self._stop_event.is_set():
                    await asyncio.sleep(1.0)
                    cur_md = self._current_md
                    if not cur_md or not cur_md.exists():
                        continue
                    try:
                        mtime = cur_md.stat().st_mtime
                    except OSError:
                        continue
                    if mtime != last_mtime:
                        last_mtime = mtime
                        self._last_mtime = mtime
                        await websocket.send_json({"type": "reload"})
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
            finally:
                clients.discard(websocket)

        self._ws_clients = clients
        return app

    # ===== 目录模式:文章列表 =====

    def _list_md_files(self) -> list[Path]:
        """扫描目录下所有 md 文件(递归),按修改时间倒序"""
        if not self.is_dir_mode:
            return [self.md_path]
        files = list(self.md_path.rglob("*.md"))
        # 按修改时间倒序(最新的在前)
        files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        return files

    def _find_md_by_stem(self, stem: str) -> Optional[Path]:
        """根据文件名 stem 查找 md 文件

        支持精确匹配 stem(如 changxin_tech_sample),
        也支持带 .md 后缀的输入。
        """
        if not self.is_dir_mode:
            return self.md_path if self.md_path.stem == stem else None
        target = stem.removesuffix(".md")
        for f in self.md_path.rglob("*.md"):
            if f.stem == target:
                return f
        return None

    def _render_list_page(self) -> str:
        """渲染文章列表页"""
        md_files = self._list_md_files()
        rows_html: list[str] = []
        for f in md_files:
            try:
                stat = f.stat()
                from datetime import datetime
                mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                size_kb = stat.st_size / 1024
            except OSError:
                mtime_str = "-"
                size_kb = 0
            # 尝试读取 front matter 的 title
            title = f.stem
            template = "minimal"
            try:
                article = self.parser.parse(f)
                if article.meta.title:
                    title = article.meta.title
                if article.meta.template:
                    template = article.meta.template
            except Exception:
                pass
            # 相对路径显示
            try:
                rel_path = f.relative_to(self.md_path).as_posix()
            except ValueError:
                rel_path = f.name
            rows_html.append(
                f'<tr>'
                f'<td><a href="/view/{f.stem}">{self._escape_html(title)}</a></td>'
                f'<td><code>{self._escape_html(template)}</code></td>'
                f'<td style="color:#888">{self._escape_html(rel_path)}</td>'
                f'<td style="color:#888">{mtime_str}</td>'
                f'<td style="color:#888;text-align:right">{size_kb:.1f} KB</td>'
                f'</tr>'
            )
        rows = "\n".join(rows_html) if rows_html else (
            '<tr><td colspan="5" style="text-align:center;color:#999;padding:40px">'
            '该目录下没有 md 文件</td></tr>'
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AAP 预览 - 文章列表</title>
<style>
body {{ font-family: -apple-system, "PingFang SC", sans-serif; background: #f5f5f5; margin: 0; padding: 24px; }}
.aap-header {{ max-width: 960px; margin: 0 auto 16px; padding: 16px 24px;
    background: #333; color: #fff; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; }}
.aap-header h1 {{ margin: 0; font-size: 18px; font-weight: 500; }}
.aap-header .meta {{ font-size: 13px; color: #aaa; }}
.aap-table-wrap {{ max-width: 960px; margin: 0 auto; background: #fff;
    border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #f2f2f2; padding: 12px 16px; text-align: left;
    font-size: 13px; color: #666; font-weight: 600; border-bottom: 1px solid #e0e0e0; }}
td {{ padding: 12px 16px; border-bottom: 1px solid #f0f0f0; font-size: 14px; }}
tr:hover {{ background: #fafafa; }}
td a {{ color: rgb(40, 77, 142); text-decoration: none; font-weight: 500; }}
td a:hover {{ text-decoration: underline; }}
code {{ background: #f2f2f2; padding: 2px 6px; border-radius: 3px; font-size: 12px; color: #c7254e; }}
</style>
</head>
<body>
<div class="aap-header">
  <h1>AAP 文章预览</h1>
  <span class="meta">共 {len(md_files)} 篇 · 目录: {self._escape_html(str(self.md_path))}</span>
</div>
<div class="aap-table-wrap">
<table>
<thead><tr>
  <th>文章标题</th><th>模板</th><th>路径</th><th>修改时间</th><th style="text-align:right">大小</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
</body>
</html>"""

    # ===== 渲染 =====

    def _render_article_html(self, md_path: Path) -> str:
        """渲染指定 md 文章为带内联样式的 HTML"""
        article = self.parser.parse(md_path)
        template_name = self.template_name or article.meta.template or "minimal"

        try:
            template = self.template_manager.load_template(template_name)
            css = self.template_manager.load_template_css(template_name)
        except FileNotFoundError:
            template = self.template_manager.load_template("minimal")
            css = self.template_manager.load_template_css("minimal")
            template_name = "minimal"

        # 章节标题图片(本地预览)
        chapter_title_urls: list[str] = []
        if template.chapter_title_images:
            img_paths = self.template_manager.list_chapter_title_images(
                template_name, template.chapter_title_images
            )
            for i, img_path in enumerate(img_paths, start=1):
                if img_path.exists():
                    chapter_title_urls.append(
                        f"/icon/{template.chapter_title_images}/{i}/{img_path.name}"
                    )

        chapter_icon_url = ""
        if not chapter_title_urls and template.chapter_icon:
            icon_path = self.template_manager.get_template_asset(
                template_name, template.chapter_icon
            )
            if icon_path and icon_path.exists():
                chapter_icon_url = f"/icon/{template.chapter_icon}"

        html = self.renderer.render_preview(
            article, template, css=css,
            chapter_icon_url=chapter_icon_url,
            chapter_title_urls=chapter_title_urls,
        )
        html = self._rewrite_local_images(html, article, md_path)
        return html

    def _render_page(self, md_path: Path) -> str:
        """渲染完整预览页面(含外壳与热重载脚本)"""
        article_html = self._render_article_html(md_path)

        if self.mode == "wechat":
            body_style = (
                "background-color: #f5f5f5; padding: 24px 0; "
                "font-family: -apple-system, sans-serif"
            )
            card_style = (
                "max-width: 640px; margin: 0 auto; background: #fff; "
                "box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius: 4px; "
                "overflow: hidden"
            )
        else:
            body_style = "background-color: #ffffff; padding: 24px"
            card_style = "max-width: 960px; margin: 0 auto"

        # 记录最新 mtime
        try:
            self._last_mtime = md_path.stat().st_mtime
        except OSError:
            pass

        # 工具栏:目录模式显示返回列表链接
        back_link = ""
        raw_link = f"/view/{md_path.stem}/raw" if self.is_dir_mode else "/raw"
        if self.is_dir_mode:
            back_link = '<a href="/">返回列表</a> · '
        toolbar_left = (
            f'AAP 预览 · {self._escape_html(md_path.name)} · 模式: {self._escape_html(self.mode)}'
        )

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AAP 预览 - {self._escape_html(md_path.name)}</title>
<style>
body {{ {body_style} }}
.aap-card {{ {card_style} }}
.aap-toolbar {{
    max-width: 640px; margin: 0 auto 16px; padding: 8px 16px;
    background: #333; color: #fff; border-radius: 4px;
    font-size: 13px; display: flex; justify-content: space-between;
}}
.aap-toolbar a {{ color: #6cf; text-decoration: none }}
.aap-status {{ font-size: 12px; color: #999; margin-top: 16px; text-align: center }}
</style>
</head>
<body>
<div class="aap-toolbar">
  <span>{toolbar_left}</span>
  <span>{back_link}<a href="{raw_link}" target="_blank">查看原始 HTML</a></span>
</div>
<div class="aap-card">
{article_html}
</div>
<div class="aap-status" id="status">就绪</div>
<script>
(function() {{
  const status = document.getElementById('status');
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws');
  ws.onopen = () => {{ status.textContent = '已连接,文件变更将自动刷新'; }};
  ws.onmessage = (ev) => {{
    try {{
      const data = JSON.parse(ev.data);
      if (data.type === 'reload') {{
        status.textContent = '检测到文件变更,刷新中...';
        setTimeout(() => location.reload(), 300);
      }}
    }} catch (e) {{}}
  }};
  ws.onclose = () => {{ status.textContent = '连接已断开'; }};
}})();
</script>
</body>
</html>"""

    def _rewrite_local_images(self, html: str, article: Article, md_path: Path) -> str:
        """将本地图片 src 重写为 /image/... 路由,便于预览访问"""
        if not article.images:
            return html

        from aap.core.html_utils import replace_image_src
        from pathlib import Path as _Path

        base_dir = md_path.parent.resolve()
        mapping: dict[str, str] = {}
        for img in article.images:
            try:
                abs_p = _Path(img.original_path)
                rel = abs_p.relative_to(base_dir)
                rel_str = str(rel).replace("\\", "/")
                mapping[img.original_path] = f"/image/{rel_str}"
                mapping[rel_str] = f"/image/{rel_str}"
            except (ValueError, OSError):
                continue

        return replace_image_src(html, mapping)

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
