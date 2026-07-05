"""配置管理器

负责加载、初始化与修改 AAP 配置文件。

配置文件优先级(高到低):
1. 项目级配置: ./.aap/config.yaml
2. 全局配置:   ~/.aap/config.yaml
3. 内置默认值(AppConfig 字段默认值)

支持点号分隔的键访问,例如 account.app_id、scf.url。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import ValidationError

from aap.core.models import AppConfig
from aap.utils.path import (
    get_global_config_path,
    get_project_config_path,
)

# 内置示例配置文件路径(随包分发)
# manager.py 位于 src/aap/config/,parents[3] 为项目根目录
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parents[3] / ".aap" / "config.example.yaml"


class ConfigManager:
    """配置管理器

    负责加载、初始化与修改 AAP 配置文件,
    支持项目级与全局级配置的合并加载。
    """

    def __init__(
        self,
        global_config_path: Optional[Path] = None,
        project_config_path: Optional[Path] = None,
    ) -> None:
        """初始化配置管理器

        Args:
            global_config_path: 全局配置文件路径(默认 ~/.aap/config.yaml)
            project_config_path: 项目配置文件路径(默认 ./.aap/config.yaml)
        """
        self.global_path = global_config_path or get_global_config_path()
        self.project_path = project_config_path or get_project_config_path()

    def load(self) -> AppConfig:
        """加载并合并配置文件,返回 AppConfig 对象

        合并顺序(后者覆盖前者):
        1. 内置默认值(AppConfig 字段默认)
        2. 全局配置 ~/.aap/config.yaml
        3. 项目配置 ./.aap/config.yaml

        Returns:
            应用配置对象

        Raises:
            ValueError: 配置文件 YAML 解析失败或字段非法
        """
        merged: dict[str, Any] = {}

        # 全局配置
        global_data = self._read_yaml(self.global_path)
        if global_data:
            merged = self._deep_merge(merged, global_data)

        # 项目配置(覆盖全局)
        project_data = self._read_yaml(self.project_path)
        if project_data:
            merged = self._deep_merge(merged, project_data)

        if not merged:
            # 无配置文件,返回默认值
            return AppConfig()

        try:
            return AppConfig(**merged)
        except ValidationError as e:
            raise ValueError(f"配置文件字段非法: {e}") from e

    def init_config(self, target: str = "global") -> Path:
        """初始化配置文件(从示例复制)

        Args:
            target: "global" 写入 ~/.aap/config.yaml;"project" 写入 ./.aap/config.yaml

        Returns:
            生成的配置文件路径

        Raises:
            FileNotFoundError: 示例配置文件不存在
            FileExistsError: 目标文件已存在(避免覆盖用户配置)
        """
        if target == "project":
            target_path = self.project_path
        else:
            target_path = self.global_path

        if target_path.exists():
            raise FileExistsError(f"配置文件已存在: {target_path}(如需覆盖请手动删除)")

        if not EXAMPLE_CONFIG_PATH.exists():
            raise FileNotFoundError(f"示例配置文件不存在: {EXAMPLE_CONFIG_PATH}")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXAMPLE_CONFIG_PATH, target_path)
        return target_path

    def set_value(self, key: str, value: str) -> None:
        """修改配置项(写入全局配置文件)

        支持点号分隔的键,如 account.app_id、scf.url。
        若键不存在会自动创建;若已存在则覆盖。

        Args:
            key: 配置键(点号分隔)
            value: 配置值(字符串,自动尝试转换为 bool/int/float)

        Raises:
            ValueError: 键格式非法或写入失败
        """
        if not key or not key.strip():
            raise ValueError("配置键不能为空")

        # 选定写入的文件:优先项目级,其次全局
        target_path = (
            self.project_path if self.project_path.exists() else self.global_path
        )
        if not target_path.exists():
            # 默认写入全局,并确保目录存在
            target_path = self.global_path
            target_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._read_yaml(target_path) or {}

        # 按点号拆分嵌套键
        parts = [p.strip() for p in key.split(".")]
        if not all(parts):
            raise ValueError(f"配置键格式非法: {key}")

        # 走到倒数第二层,设置最后一层
        cursor: dict[str, Any] = data
        for part in parts[:-1]:
            if part not in cursor or not isinstance(cursor[part], dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = self._coerce_value(value)

        # 写回文件
        self._write_yaml(target_path, data)

    def get_value(self, key: str) -> Any:
        """读取配置项(从合并后的配置中取值)

        Args:
            key: 配置键(点号分隔,如 account.app_id)

        Returns:
            配置值;键不存在返回 None
        """
        config = self.load()
        cursor: Any = config
        for part in key.split("."):
            if hasattr(cursor, part):
                cursor = getattr(cursor, part)
            elif isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                return None
        return cursor

    # ===== 内部工具 =====

    def _read_yaml(self, path: Path) -> Optional[dict]:
        """读取 YAML 文件为字典,文件不存在或为空返回 None"""
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if not text.strip():
            return None
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 解析失败: {path}: {e}") from e
        return data if isinstance(data, dict) else None

    def _write_yaml(self, path: Path, data: dict) -> None:
        """将字典写入 YAML 文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(text, encoding="utf-8")

    def _deep_merge(self, base: dict, overlay: dict) -> dict:
        """递归合并两个字典,overlay 覆盖 base"""
        result = dict(base)
        for k, v in overlay.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _coerce_value(self, value: str) -> Any:
        """尝试将字符串值转换为 bool/int/float,失败则保留字符串"""
        if not isinstance(value, str):
            return value
        low = value.strip().lower()
        if low in ("true", "yes", "on"):
            return True
        if low in ("false", "no", "off"):
            return False
        # 整数
        try:
            return int(value)
        except ValueError:
            pass
        # 浮点
        try:
            return float(value)
        except ValueError:
            pass
        return value
