"""AAP 核心数据模型

定义文章、模板、配置、发布结果等 Pydantic 模型。
所有模型字段均使用 Optional 与默认值,便于增量构建。
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ArticleMeta(BaseModel):
    """文章元信息(来自 Front Matter)"""

    title: str = ""
    author: str = ""
    summary: str = ""
    cover: str = ""
    tags: list[str] = Field(default_factory=list)
    template: str = ""
    category: str = ""


class ImageRef(BaseModel):
    """图片引用信息"""

    index: int = 0
    original_path: str = ""
    alt: str = ""
    packed_name: str = ""
    wechat_media_id: str = ""
    wechat_url: str = ""
    placeholder: str = ""


class Article(BaseModel):
    """完整文章对象"""

    meta: ArticleMeta = Field(default_factory=ArticleMeta)
    content_html: str = ""
    source_path: Optional[Path] = None
    images: list[ImageRef] = Field(default_factory=list)


class TypographyConfig(BaseModel):
    """排版配置"""

    font_family: str = ""
    base_size: str = ""
    base_color: str = ""
    line_height: str = ""
    heading_color: str = ""
    link_color: str = ""
    code_color: str = ""


class SpacingConfig(BaseModel):
    """间距配置"""

    paragraph_margin: str = ""
    first_line_indent: str = ""
    left_right_padding: str = ""
    background_color: str = ""


class ImageStyleConfig(BaseModel):
    """图片样式配置"""

    max_width: str = ""
    border_radius: str = ""
    shadow: str = ""
    caption_color: str = ""
    caption_size: str = ""


class TableConfig(BaseModel):
    """表格配置"""

    border_color: str = ""
    header_background: str = ""
    zebra_striped: bool = False
    zebra_color: str = ""


class CodeBlockConfig(BaseModel):
    """代码块配置"""

    theme: str = ""
    background: str = ""
    font_size: str = ""
    line_numbers: bool = False


class TemplateConfig(BaseModel):
    """模板配置"""

    name: str = ""
    description: str = ""
    typography: TypographyConfig = Field(default_factory=TypographyConfig)
    spacing: SpacingConfig = Field(default_factory=SpacingConfig)
    image: ImageStyleConfig = Field(default_factory=ImageStyleConfig)
    table: TableConfig = Field(default_factory=TableConfig)
    code_block: CodeBlockConfig = Field(default_factory=CodeBlockConfig)
    # 章节标题装饰小图标(单个文件名,放在模板目录下,所有章节共用)
    chapter_icon: str = ""
    # 章节标题整图目录(模板目录下的子目录,内含 1.png~N.png,按 H1 出现顺序匹配)
    chapter_title_images: str = ""


class PublishResult(BaseModel):
    """API 发布结果"""

    success: bool = False
    draft_media_id: str = ""
    thumb_media_id: str = ""
    image_count: int = 0
    error: str = ""
    article_title: str = ""


class ExportResult(BaseModel):
    """手动导出结果"""

    success: bool = False
    output_dir: Optional[Path] = None
    html_path: Optional[Path] = None
    images_zip_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    instructions_path: Optional[Path] = None
    image_count: int = 0


class AccountConfig(BaseModel):
    """微信公众号账号配置"""

    app_id: str = ""
    app_secret: str = ""
    nickname: str = ""


class SCFConfig(BaseModel):
    """腾讯云 SCF 配置"""

    url: str = ""
    secret: str = ""
    enabled: bool = False


class PreviewConfig(BaseModel):
    """预览配置"""

    port: int = 8000
    default_mode: str = "wechat"
    open_browser: bool = True


class PublishConfig(BaseModel):
    """发布配置"""

    output_dir: str = ".aap/output"
    auto_clipboard: bool = True


class EditorConfig(BaseModel):
    """模板编辑器配置"""

    port: int = 7000
    sample_article: str = ""


class HistoryConfig(BaseModel):
    """历史记录配置"""

    enabled: bool = True
    file: str = ".aap/history.jsonl"


class AppConfig(BaseModel):
    """应用总配置"""

    account: AccountConfig = Field(default_factory=AccountConfig)
    scf: SCFConfig = Field(default_factory=SCFConfig)
    default_template: str = "minimal"
    preview: PreviewConfig = Field(default_factory=PreviewConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)


class TokenCache(BaseModel):
    """微信 access_token 缓存"""

    access_token: str = ""
    expires_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
