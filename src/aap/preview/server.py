"""本地预览服务

基于 FastAPI 提供文章渲染效果预览,支持:
- wechat 模式: 模拟微信编辑器外观(白底、内联样式)
- html 模式:   纯 HTML 预览(便于调试)
- 文件监听与热重载(WebSocket 推送)

启动方式:
    PreviewServer(md_path, mode="wechat", port=7788).start()
"""
from __future__ import annotations

import asyncio
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse

from aap.core.models import Article
from aap.core.parser import ArticleParser
from aap.core.renderer import HTMLRenderer
from aap.templates.manager import TemplateManager


class PreviewServer:
    """本地预览服务

    基于 FastAPI + WebSocket 提供文章渲染效果预览与热重载,
    支持 wechat/html/screenshot 三种模式。
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
            md_path: Markdown 文件路径
            mode: 预览模式(wechat/html/screenshot)
            port: 监听端口
            open_browser: 是否自动打开浏览器
            template_name: 指定模板名(覆盖 Front Matter)
        """
        self.md_path = Path(md_path).resolve()
        self.mode = mode
        self.port = port
        self.open_browser = open_browser
        self.template_name = template_name

        self.parser = ArticleParser()
        self.template_manager = TemplateManager()
        self.renderer = HTMLRenderer()

        self.app: Optional[FastAPI] = None
        self._last_mtime: float = 0.0
        self._stop_event = threading.Event()

    def start(self) -> None:
        """启动预览服务(阻塞)

        启动流程:
        1. 构建 FastAPI 应用
        2. (可选)自动打开浏览器
        3. uvicorn 启动服务,WebSocket 端点内自动轮询文件变更
        """
        self.app = self._build_app()

        # 打开浏览器
        if self.open_browser:
            url = f"http://127.0.0.1:{self.port}"
            # 异步打开,避免阻塞 uvicorn 启动
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

        # 存放 WebSocket 连接
        clients: set[WebSocket] = set()

        @app.get("/", response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            """渲染文章预览页面"""
            html = self._render_page()
            return HTMLResponse(html)

        @app.get("/raw", response_class=HTMLResponse)
        async def raw() -> HTMLResponse:
            """返回原始渲染 HTML(无预览外壳,便于复制)"""
            html = self._render_article_html()
            return HTMLResponse(html)

        @app.get("/image/{path:path}")
        async def serve_image(path: str):
            """提供本地图片访问(预览模式保留原 src)"""
            # 限制在 md 所在目录下,防止目录穿越
            base = self.md_path.parent.resolve()
            target = (base / path).resolve()
            try:
                target.relative_to(base)
            except ValueError:
                return HTMLResponse("Forbidden", status_code=403)
            if not target.exists() or not target.is_file():
                return HTMLResponse("Not Found", status_code=404)
            return FileResponse(target)

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket 热重载端点

            在事件循环内主动轮询文件 mtime,变更则推送 reload。
            不依赖外部线程,避免跨事件循环调用问题。
            """
            await websocket.accept()
            clients.add(websocket)
            last_mtime = self._last_mtime
            try:
                while not self._stop_event.is_set():
                    await asyncio.sleep(1.0)
                    try:
                        mtime = self.md_path.stat().st_mtime
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

        # 暴露 clients 给 watcher(兼容性保留,目前未使用)
        self._ws_clients = clients

        return app

    # ===== 渲染 =====

    def _render_article_html(self) -> str:
        """渲染文章为带内联样式的 HTML(预览模式,保留原 src)"""
        article = self.parser.parse(self.md_path)
        template_name = self.template_name or article.meta.template or "minimal"

        try:
            template = self.template_manager.load_template(template_name)
            css = self.template_manager.load_template_css(template_name)
        except FileNotFoundError:
            template = self.template_manager.load_template("minimal")
            css = self.template_manager.load_template_css("minimal")

        # 预览模式:保留原 src,但把相对路径转换为 /image/... 路由
        html = self.renderer.render_preview(article, template, css=css)
        html = self._rewrite_local_images(html, article)
        return html

    def _render_page(self) -> str:
        """渲染完整预览页面(含外壳与热重载脚本)"""
        article_html = self._render_article_html()

        if self.mode == "wechat":
            # 微信编辑器外观模拟:白底卡片居中
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
            self._last_mtime = self.md_path.stat().st_mtime
        except OSError:
            pass

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AAP 预览 - {self._escape_html(self.md_path.name)}</title>
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
  <span>AAP 预览 · {self._escape_html(self.md_path.name)} · 模式: {self._escape_html(self.mode)}</span>
  <span><a href="/raw" target="_blank">查看原始 HTML</a></span>
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

    def _rewrite_local_images(self, html: str, article: Article) -> str:
        """将本地图片 src 重写为 /image/... 路由,便于预览访问"""
        if not article.images:
            return html

        from aap.core.html_utils import replace_image_src
        from pathlib import Path as _Path

        base_dir = self.md_path.parent.resolve()
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
