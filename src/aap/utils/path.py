"""路径工具函数

提供路径展开、AAP 主目录与配置文件路径等工具函数。
所有函数为纯函数,无副作用,可独立单测。
"""
from __future__ import annotations

import os
from pathlib import Path


def expand_path(p: str | Path) -> Path:
    """展开路径中的 ~ 与环境变量

    Args:
        p: 原始路径字符串或 Path 对象

    Returns:
        展开后的绝对 Path 对象
    """
    if isinstance(p, Path):
        # Path 对象直接 expanduser
        return p.expanduser().resolve()
    # 字符串先展开环境变量与 ~
    expanded = os.path.expandvars(os.path.expanduser(str(p)))
    return Path(expanded).resolve()


def get_aap_home() -> Path:
    """获取 AAP 用户主目录

    Returns:
        AAP 主目录 Path 对象(~/.aap)
    """
    return Path.home() / ".aap"


def get_global_config_path() -> Path:
    """获取全局配置文件路径

    Returns:
        全局配置文件 Path 对象(~/.aap/config.yaml)
    """
    return get_aap_home() / "config.yaml"


def get_project_config_path() -> Path:
    """获取项目级配置文件路径

    Returns:
        项目配置文件 Path 对象(./.aap/config.yaml)
    """
    return Path(".aap") / "config.yaml"


def get_token_cache_path() -> Path:
    """获取 access_token 缓存文件路径

    Returns:
        token 缓存文件 Path 对象(~/.aap/token_cache.json)
    """
    return get_aap_home() / "token_cache.json"


def get_history_path(file_path: str | None = None) -> Path:
    """获取发布历史文件路径

    Args:
        file_path: 自定义历史文件路径(可为 ~ 或相对路径),为空时使用默认值

    Returns:
        历史文件 Path 对象
    """
    if file_path:
        return expand_path(file_path)
    return get_aap_home() / "history.jsonl"


def ensure_aap_home() -> Path:
    """确保 AAP 主目录存在,返回路径

    Returns:
        AAP 主目录 Path 对象
    """
    home = get_aap_home()
    home.mkdir(parents=True, exist_ok=True)
    return home
