"""模板管理器

负责列出、加载、保存模板,以及为文章解析应使用的模板。

模板查找优先级(高到低):
1. 项目本地模板: ./.aap/templates/<name>/
2. 全局用户模板: ~/.aap/templates/<name>/
3. 内置模板:      aap.templates.builtin/<name>/

每个模板目录包含:
- template.yaml  : TemplateConfig 配置
- style.css      : CSS 样式(用于内联到 HTML)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from aap.core.models import (
    Article,
    CodeBlockConfig,
    ImageStyleConfig,
    SpacingConfig,
    TableConfig,
    TemplateConfig,
    TypographyConfig,
)

# 内置模板目录(本文件所在目录的 builtin 子目录)
BUILTIN_TEMPLATES_DIR = Path(__file__).parent / "builtin"


class TemplateManager:
    """模板管理器

    负责列出、加载、保存模板,以及为文章解析应使用的模板。
    """

    def __init__(
        self,
        project_templates_dir: Optional[Path] = None,
        user_templates_dir: Optional[Path] = None,
        default_template: str = "minimal",
    ) -> None:
        """初始化模板管理器

        Args:
            project_templates_dir: 项目本地模板目录,默认 ./.aap/templates
            user_templates_dir: 用户全局模板目录,默认 ~/.aap/templates
            default_template: 默认模板名称
        """
        self.project_dir = project_templates_dir or Path.cwd() / ".aap" / "templates"
        self.user_dir = user_templates_dir or Path.home() / ".aap" / "templates"
        self.default_template = default_template

    def list_templates(self) -> list[str]:
        """列出所有可用模板名称(去重)

        Returns:
            模板名称列表(包含内置与用户模板),按字母序排序
        """
        names: set[str] = set()

        # 内置模板
        if BUILTIN_TEMPLATES_DIR.exists():
            for d in BUILTIN_TEMPLATES_DIR.iterdir():
                if d.is_dir() and (d / "template.yaml").exists():
                    names.add(d.name)

        # 用户全局模板
        if self.user_dir.exists():
            for d in self.user_dir.iterdir():
                if d.is_dir() and (d / "template.yaml").exists():
                    names.add(d.name)

        # 项目本地模板
        if self.project_dir.exists():
            for d in self.project_dir.iterdir():
                if d.is_dir() and (d / "template.yaml").exists():
                    names.add(d.name)

        return sorted(names)

    def load_template(self, name: str) -> TemplateConfig:
        """加载指定模板配置

        优先级: 项目 > 全局 > 内置

        Args:
            name: 模板名称

        Returns:
            模板配置对象

        Raises:
            FileNotFoundError: 模板不存在
            ValueError: 模板配置格式错误
        """
        template_dir = self._find_template_dir(name)
        if template_dir is None:
            raise FileNotFoundError(f"模板不存在: {name}")

        config_path = template_dir / "template.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"模板配置文件不存在: {config_path}")

        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ValueError(f"模板 YAML 解析失败: {config_path}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"模板配置必须是字典: {config_path}")

        return self._build_config(data)

    def load_template_css(self, name: str) -> str:
        """加载指定模板的 CSS 样式文本

        Args:
            name: 模板名称

        Returns:
            CSS 文本,若无 style.css 则返回空字符串
        """
        template_dir = self._find_template_dir(name)
        if template_dir is None:
            raise FileNotFoundError(f"模板不存在: {name}")
        css_path = template_dir / "style.css"
        if not css_path.exists():
            return ""
        return css_path.read_text(encoding="utf-8")

    def save_template(self, name: str, config: TemplateConfig, css: str) -> Path:
        """保存模板配置与样式到用户全局目录

        Args:
            name: 模板名称
            config: 模板配置
            css: CSS 样式文本

        Returns:
            保存的模板目录路径
        """
        template_dir = self.user_dir / name
        template_dir.mkdir(parents=True, exist_ok=True)

        # 写入 template.yaml
        config_data = config.model_dump()
        config_path = template_dir / "template.yaml"
        config_path.write_text(
            yaml.safe_dump(config_data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        # 写入 style.css
        css_path = template_dir / "style.css"
        css_path.write_text(css, encoding="utf-8")

        return template_dir

    def resolve_template(
        self, article: Article, cli_override: Optional[str] = None
    ) -> TemplateConfig:
        """解析文章应使用的模板

        优先级: CLI 参数 > Front Matter > 默认模板

        Args:
            article: 文章对象
            cli_override: 命令行指定的模板名

        Returns:
            模板配置对象
        """
        name = cli_override or article.meta.template or self.default_template
        try:
            return self.load_template(name)
        except FileNotFoundError:
            # 回退到默认模板
            if name != self.default_template:
                return self.load_template(self.default_template)
            raise

    def resolve_template_name(
        self, article: Article, cli_override: Optional[str] = None
    ) -> str:
        """解析文章应使用的模板名称(不加载配置)

        优先级: CLI 参数 > Front Matter > 默认模板
        """
        return cli_override or article.meta.template or self.default_template

    def get_template_asset(self, name: str, asset_filename: str) -> Optional[Path]:
        """获取模板目录下的资源文件路径(如章节图标)

        Args:
            name: 模板名称
            asset_filename: 资源文件名(如 chapter_icon.png)

        Returns:
            文件路径(若存在),否则 None
        """
        template_dir = self._find_template_dir(name)
        if template_dir is None:
            return None
        asset_path = template_dir / asset_filename
        return asset_path if asset_path.exists() else None

    def list_chapter_title_images(self, name: str, sub_dir: str) -> list[Path]:
        """列出章节标题整图目录下的所有图片,按文件名数字序排序

        Args:
            name: 模板名称
            sub_dir: 模板目录下的子目录名(如 chapter_titles)

        Returns:
            图片文件路径列表(按 1.png, 2.png, ... 顺序),空列表表示无图片
        """
        template_dir = self._find_template_dir(name)
        if template_dir is None:
            return []
        img_dir = template_dir / sub_dir
        if not img_dir.exists() or not img_dir.is_dir():
            return []
        # 收集 .png/.jpg/.jpeg 文件,按文件名中的数字排序
        import re as _re
        files: list[tuple[int, Path]] = []
        for f in img_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            m = _re.search(r"(\d+)", f.stem)
            order = int(m.group(1)) if m else 0
            files.append((order, f))
        files.sort(key=lambda x: x[0])
        return [p for _, p in files]

    # ===== 内部工具 =====

    def _find_template_dir(self, name: str) -> Optional[Path]:
        """按优先级查找模板目录"""
        # 1. 项目本地
        project = self.project_dir / name
        if (project / "template.yaml").exists():
            return project
        # 2. 用户全局
        user = self.user_dir / name
        if (user / "template.yaml").exists():
            return user
        # 3. 内置
        builtin = BUILTIN_TEMPLATES_DIR / name
        if (builtin / "template.yaml").exists():
            return builtin
        return None

    def _build_config(self, data: dict) -> TemplateConfig:
        """从字典构造 TemplateConfig,处理嵌套子配置"""
        try:
            return TemplateConfig(
                name=str(data.get("name", "")),
                description=str(data.get("description", "")),
                typography=TypographyConfig(**(data.get("typography") or {})),
                spacing=SpacingConfig(**(data.get("spacing") or {})),
                image=ImageStyleConfig(**(data.get("image") or {})),
                table=TableConfig(**(data.get("table") or {})),
                code_block=CodeBlockConfig(**(data.get("code_block") or {})),
                chapter_icon=str(data.get("chapter_icon", "")),
                chapter_title_images=str(data.get("chapter_title_images", "")),
            )
        except (ValidationError, TypeError) as e:
            raise ValueError(f"模板配置格式错误: {e}") from e
