"""模板可视化编辑器服务

基于 FastAPI 提供可视化编辑模板样式的能力,支持实时预览。

提供以下能力:
- 列出/加载/保存模板配置与 CSS
- 在线编辑 CSS 与 YAML 配置
- 实时预览渲染效果(基于示例文章或用户指定文章)
- WebSocket 推送预览刷新

启动方式:
    EditorServer(template_name="minimal", port=7000).start()
"""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any, Optional

import uvicorn
import yaml
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from aap.core.models import (
    CodeBlockConfig,
    ImageStyleConfig,
    SpacingConfig,
    TableConfig,
    TemplateConfig,
    TypographyConfig,
)
from aap.core.parser import ArticleParser
from aap.core.renderer import HTMLRenderer
from aap.templates.manager import TemplateManager

# 默认示例文章路径(项目内 fixtures)
# server.py 位于 src/aap/templates/editor/,parents[4] 为项目根目录
_DEFAULT_SAMPLE = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "minimal" / "sample.md"


class EditorServer:
    """模板可视化编辑器

    基于 FastAPI 提供可视化编辑模板样式的能力,支持实时预览。
    """

    def __init__(
        self,
        port: int = 7000,
        sample_article: Optional[Path] = None,
        template_name: Optional[str] = None,
        open_browser: bool = True,
    ) -> None:
        """初始化编辑器服务

        Args:
            port: 监听端口
            sample_article: 示例文章路径,用于实时预览(为 None 时使用默认 fixtures)
            template_name: 启动时加载的模板名(为 None 时使用 default_template)
            open_browser: 是否自动打开浏览器
        """
        self.port = port
        self.sample_article = Path(sample_article).resolve() if sample_article else _DEFAULT_SAMPLE
        self.template_name = template_name
        self.open_browser = open_browser

        self.parser = ArticleParser()
        self.renderer = HTMLRenderer()
        self.template_manager = TemplateManager()

        self.app: Optional[FastAPI] = None
        self._ws_clients: set[WebSocket] = set()
        self._stop_event = threading.Event()

    def start(self) -> None:
        """启动编辑器服务(阻塞)

        启动流程:
        1. 构建 FastAPI 应用
        2. (可选)自动打开浏览器
        3. uvicorn 启动服务
        """
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
        """构建 FastAPI 应用与路由"""
        app = FastAPI(title="AAP Template Editor", docs_url=None, redoc_url=None)

        @app.get("/", response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            return HTMLResponse(self._render_editor_page())

        @app.get("/api/templates")
        async def list_templates() -> dict:
            names = self.template_manager.list_templates()
            default_name = self.template_name or self.template_manager.default_template
            return {"templates": names, "default": default_name}

        @app.get("/api/templates/{name}")
        async def get_template(name: str) -> JSONResponse:
            try:
                config = self.template_manager.load_template(name)
                css = self.template_manager.load_template_css(name)
            except FileNotFoundError as e:
                return JSONResponse({"error": str(e)}, status_code=404)
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)

            config_data = config.model_dump()
            yaml_text = yaml.safe_dump(config_data, allow_unicode=True, sort_keys=False)
            return {"name": name, "config_yaml": yaml_text, "css": css}

        @app.post("/api/templates/{name}")
        async def save_template(name: str, request: Request) -> JSONResponse:
            try:
                payload = await request.json()
            except ValueError:
                return JSONResponse({"error": "请求体必须是 JSON"}, status_code=400)

            css = str(payload.get("css", ""))
            config_yaml = str(payload.get("config_yaml", ""))

            try:
                data = yaml.safe_load(config_yaml) or {}
            except yaml.YAMLError as e:
                return JSONResponse({"error": f"YAML 解析失败: {e}"}, status_code=400)

            if not isinstance(data, dict):
                return JSONResponse({"error": "配置必须是字典"}, status_code=400)

            try:
                config = self._build_config(data, name)
            except (ValidationError, TypeError, ValueError) as e:
                return JSONResponse({"error": f"配置格式错误: {e}"}, status_code=400)

            try:
                saved_path = self.template_manager.save_template(name, config, css)
            except OSError as e:
                return JSONResponse({"error": f"保存失败: {e}"}, status_code=500)

            await self._broadcast({"type": "saved", "name": name})
            return {
                "name": name,
                "saved_path": str(saved_path),
                "message": "保存成功",
            }

        @app.post("/api/preview")
        async def render_preview(request: Request) -> JSONResponse:
            try:
                payload = await request.json()
            except ValueError:
                return JSONResponse({"error": "请求体必须是 JSON"}, status_code=400)

            css = str(payload.get("css", ""))
            config_yaml = str(payload.get("config_yaml", ""))

            try:
                data = yaml.safe_load(config_yaml) or {}
            except yaml.YAMLError as e:
                return JSONResponse({"error": f"YAML 解析失败: {e}"}, status_code=400)

            if not isinstance(data, dict):
                return JSONResponse({"error": "配置必须是字典"}, status_code=400)

            try:
                config = self._build_config(data, payload.get("name") or "preview")
            except (ValidationError, TypeError, ValueError) as e:
                return JSONResponse({"error": f"配置格式错误: {e}"}, status_code=400)

            try:
                html = self._render_preview_html(config, css)
            except FileNotFoundError as e:
                return JSONResponse({"error": str(e)}, status_code=404)
            except Exception as e:  # 渲染异常时返回错误信息便于调试
                return JSONResponse({"error": f"渲染失败: {e}"}, status_code=500)

            return {"html": html}

        @app.get("/api/sample")
        async def sample_info() -> dict:
            return {
                "sample_article": str(self.sample_article),
                "exists": self.sample_article.exists(),
            }

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            await websocket.accept()
            self._ws_clients.add(websocket)
            try:
                # 仅维持连接,服务端推送用
                while not self._stop_event.is_set():
                    try:
                        await websocket.receive_text()
                    except WebSocketDisconnect:
                        break
            except WebSocketDisconnect:
                pass
            except Exception:
                pass
            finally:
                self._ws_clients.discard(websocket)

        return app

    # ===== 渲染 =====

    def _render_preview_html(self, config: TemplateConfig, css: str) -> str:
        """根据当前编辑的配置与 CSS 渲染预览 HTML"""
        if not self.sample_article.exists():
            raise FileNotFoundError(f"示例文章不存在: {self.sample_article}")

        article = self.parser.parse(self.sample_article)
        # 预览模式: 保留原 src,以便本地图片可见
        return self.renderer.render_preview(article, config, css=css)

    def _render_editor_page(self) -> str:
        """渲染编辑器主页面"""
        sample_path = str(self.sample_article)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AAP 模板编辑器</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
.header {{
  background: #1a1a1a; color: #fff; padding: 10px 20px;
  display: flex; justify-content: space-between; align-items: center;
}}
.header h1 {{ margin: 0; font-size: 16px; font-weight: normal; }}
.header .actions button {{ margin-left: 8px; padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }}
.btn-primary {{ background: #07c160; color: #fff; }}
.btn-secondary {{ background: #444; color: #fff; }}
.main {{ display: flex; height: calc(100vh - 48px); }}
.left-panel {{ width: 50%; display: flex; flex-direction: column; border-right: 1px solid #ddd; background: #fff; }}
.right-panel {{ width: 50%; background: #f0f0f0; overflow: auto; padding: 16px; }}
.tabs {{ display: flex; background: #fafafa; border-bottom: 1px solid #ddd; }}
.tab {{
  padding: 8px 16px; cursor: pointer; border-right: 1px solid #ddd;
  font-size: 13px; color: #666;
}}
.tab.active {{ background: #fff; color: #07c160; font-weight: bold; }}
.editor-area {{ flex: 1; display: flex; }}
.editor-area textarea {{
  flex: 1; width: 100%; border: none; outline: none; padding: 12px;
  font-family: 'Consolas', 'Monaco', monospace; font-size: 13px;
  resize: none; line-height: 1.5;
}}
.editor-area textarea.hidden {{ display: none; }}
.toolbar {{
  padding: 6px 12px; background: #fafafa; border-bottom: 1px solid #ddd;
  display: flex; align-items: center; gap: 10px; font-size: 13px;
}}
.toolbar select {{ padding: 4px 8px; border: 1px solid #ccc; border-radius: 3px; }}
.toolbar .status {{ color: #888; margin-left: auto; }}
.preview-frame {{
  background: #fff; max-width: 640px; margin: 0 auto;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius: 4px;
  padding: 16px; min-height: 400px;
}}
.error-box {{
  background: #fff3f3; border: 1px solid #ffcccc; color: #cc0000;
  padding: 10px; border-radius: 4px; margin-bottom: 10px;
  font-size: 13px; display: none;
}}
</style>
</head>
<body>
<div class="header">
  <h1>AAP 模板编辑器</h1>
  <div class="actions">
    <button id="btn-preview" class="btn-secondary">预览 (Ctrl+S)</button>
    <button id="btn-save" class="btn-primary">保存</button>
  </div>
</div>
<div class="toolbar">
  <label>模板:</label>
  <select id="template-select"></select>
  <span class="status" id="status">就绪</span>
</div>
<div class="error-box" id="error-box"></div>
<div class="main">
  <div class="left-panel">
    <div class="tabs">
      <div class="tab active" data-tab="css">CSS</div>
      <div class="tab" data-tab="yaml">配置 YAML</div>
    </div>
    <div class="editor-area">
      <textarea id="editor-css" spellcheck="false" placeholder="/* 在此编辑 CSS */"></textarea>
      <textarea id="editor-yaml" spellcheck="false" class="hidden" placeholder="# 在此编辑模板配置 YAML"></textarea>
    </div>
  </div>
  <div class="right-panel">
    <div class="preview-frame" id="preview-frame">
      <p style="color:#999;text-align:center;">点击右上角"预览"按钮查看渲染效果</p>
    </div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
const select = $('template-select');
const cssEditor = $('editor-css');
const yamlEditor = $('editor-yaml');
const previewFrame = $('preview-frame');
const errorBox = $('error-box');
const statusEl = $('status');
let currentName = '';

function showError(msg) {{
  if (!msg) {{ errorBox.style.display = 'none'; return; }}
  errorBox.textContent = msg;
  errorBox.style.display = 'block';
}}

function setStatus(text) {{ statusEl.textContent = text; }}

async function loadTemplates() {{
  const resp = await fetch('/api/templates');
  const data = await resp.json();
  select.innerHTML = '';
  for (const name of data.templates) {{
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    select.appendChild(opt);
  }}
  if (data.default && data.templates.includes(data.default)) {{
    select.value = data.default;
  }} else if (data.templates.length > 0) {{
    select.value = data.templates[0];
  }}
  await loadTemplate(select.value);
}}

async function loadTemplate(name) {{
  if (!name) return;
  setStatus('加载模板 ' + name + '...');
  const resp = await fetch('/api/templates/' + encodeURIComponent(name));
  const data = await resp.json();
  if (!resp.ok) {{ showError(data.error || '加载失败'); return; }}
  currentName = name;
  cssEditor.value = data.css || '';
  yamlEditor.value = data.config_yaml || '';
  setStatus('已加载 ' + name);
  showError('');
  await renderPreview();
}}

async function renderPreview() {{
  const body = {{
    name: currentName,
    css: cssEditor.value,
    config_yaml: yamlEditor.value,
  }};
  const resp = await fetch('/api/preview', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }});
  const data = await resp.json();
  if (!resp.ok) {{ showError(data.error || '渲染失败'); return; }}
  previewFrame.innerHTML = data.html || '';
  showError('');
  setStatus('预览已更新');
}}

async function saveTemplate() {{
  if (!currentName) {{ showError('未选择模板'); return; }}
  const body = {{
    css: cssEditor.value,
    config_yaml: yamlEditor.value,
  }};
  const resp = await fetch('/api/templates/' + encodeURIComponent(currentName), {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }});
  const data = await resp.json();
  if (!resp.ok) {{ showError(data.error || '保存失败'); return; }}
  showError('');
  setStatus(data.message || '保存成功');
}}

// 事件绑定
select.addEventListener('change', () => loadTemplate(select.value));
$('btn-preview').addEventListener('click', renderPreview);
$('btn-save').addEventListener('click', saveTemplate);

document.addEventListener('keydown', (e) => {{
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {{
    e.preventDefault();
    renderPreview();
  }}
}});

document.querySelectorAll('.tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.tab;
    cssEditor.classList.toggle('hidden', target !== 'css');
    yamlEditor.classList.toggle('hidden', target !== 'yaml');
  }});
}});

// WebSocket 接收保存通知
const ws = new WebSocket((location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws');
ws.onmessage = (ev) => {{
  try {{
    const data = JSON.parse(ev.data);
    if (data.type === 'saved') setStatus('模板 ' + data.name + ' 已保存');
  }} catch (e) {{}}
}};

// 初始化
loadTemplates().catch(err => showError('初始化失败: ' + err));
</script>
</body>
</html>"""

    # ===== 内部工具 =====

    def _build_config(self, data: dict, name: str) -> TemplateConfig:
        """从字典构造 TemplateConfig,处理嵌套子配置"""
        return TemplateConfig(
            name=str(data.get("name", name)),
            description=str(data.get("description", "")),
            typography=TypographyConfig(**(data.get("typography") or {})),
            spacing=SpacingConfig(**(data.get("spacing") or {})),
            image=ImageStyleConfig(**(data.get("image") or {})),
            table=TableConfig(**(data.get("table") or {})),
            code_block=CodeBlockConfig(**(data.get("code_block") or {})),
        )

    async def _broadcast(self, message: dict) -> None:
        """向所有 WebSocket 客户端推送消息"""
        dead: list[WebSocket] = []
        for ws in list(self._ws_clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)
