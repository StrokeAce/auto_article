"""Jinja2 模板引擎封装

封装模板加载与渲染逻辑,支持从文件系统加载模板。

当前 AAP 的核心渲染由 HTMLRenderer + html_utils 完成(直接操作 BeautifulSoup),
TemplateEngine 主要用于:
- 渲染预览页面外壳(可扩展)
- 渲染导出指引文档模板
- 未来扩展(如自定义 HTML 骨架)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape


class TemplateEngine:
    """Jinja2 模板引擎

    封装模板加载与渲染逻辑,支持从文件系统加载模板。
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        autoescape: bool = True,
    ) -> None:
        """初始化模板引擎

        Args:
            template_dir: 模板目录路径,默认使用内置模板目录
            autoescape: 是否开启 HTML 自动转义(默认 True)
        """
        if template_dir is None:
            template_dir = Path(__file__).resolve().parents[1] / "templates" / "builtin"
        self.template_dir = Path(template_dir)

        loaders = []
        if self.template_dir.exists():
            loaders.append(FileSystemLoader(str(self.template_dir)))
        # 提供 DictLoader 兜底,避免目录不存在时初始化失败
        from jinja2 import DictLoader, ChoiceLoader
        self._fallback_templates: dict[str, str] = {}
        loaders.append(DictLoader(self._fallback_templates))

        self.env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
            keep_trailing_newline=True,
            trim_blocks=False,
            lstrip_blocks=False,
        )

    def render(self, template_name: str, context: dict) -> str:
        """渲染指定模板

        Args:
            template_name: 模板文件名(相对 template_dir)
            context: 渲染上下文变量

        Returns:
            渲染后的字符串

        Raises:
            jinja2.TemplateNotFound: 模板不存在
        """
        template = self.env.get_template(template_name)
        return template.render(**context)

    def render_string(self, template_str: str, context: dict) -> str:
        """渲染字符串模板(不从文件加载)

        Args:
            template_str: 模板字符串
            context: 渲染上下文

        Returns:
            渲染后的字符串
        """
        template = self.env.from_string(template_str)
        return template.render(**context)

    def list_templates(self) -> list[str]:
        """列出所有可用模板名"""
        return sorted(self.env.list_templates())

    def add_template(self, name: str, content: str) -> None:
        """动态添加一个模板(不写入磁盘)

        Args:
            name: 模板名
            content: 模板内容
        """
        self._fallback_templates[name] = content

    def has_template(self, name: str) -> bool:
        """判断模板是否存在"""
        try:
            self.env.get_template(name)
            return True
        except Exception:
            return False
