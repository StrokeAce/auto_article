"""ConfigManager 测试"""
from pathlib import Path

import pytest
import yaml

from aap.config.manager import ConfigManager
from aap.core.models import AppConfig


def test_load_no_config_files(tmp_path: Path) -> None:
    """无配置文件时返回默认 AppConfig"""
    manager = ConfigManager(
        global_config_path=tmp_path / "global.yaml",
        project_config_path=tmp_path / "project.yaml",
    )
    config = manager.load()
    assert isinstance(config, AppConfig)
    assert config.default_template == "minimal"
    assert config.scf.enabled is False


def test_load_global_config(tmp_path: Path) -> None:
    """加载全局配置"""
    global_path = tmp_path / "global.yaml"
    global_path.write_text(
        "default_template: custom\n"
        "account:\n  app_id: g-id\n  app_secret: g-secret\n",
        encoding="utf-8",
    )
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    config = manager.load()
    assert config.default_template == "custom"
    assert config.account.app_id == "g-id"


def test_load_project_overrides_global(tmp_path: Path) -> None:
    """项目配置覆盖全局配置"""
    global_path = tmp_path / "global.yaml"
    global_path.write_text(
        "account:\n  app_id: g-id\n  app_secret: g-secret\n",
        encoding="utf-8",
    )
    project_path = tmp_path / "project.yaml"
    project_path.write_text(
        "account:\n  app_id: p-id\n",
        encoding="utf-8",
    )
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=project_path,
    )
    config = manager.load()
    # 项目覆盖全局
    assert config.account.app_id == "p-id"
    # 但 app_secret 保留全局值(深度合并)
    assert config.account.app_secret == "g-secret"


def test_load_invalid_yaml(tmp_path: Path) -> None:
    """非法 YAML 抛 ValueError"""
    global_path = tmp_path / "global.yaml"
    global_path.write_text("foo: [unclosed", encoding="utf-8")
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    with pytest.raises(ValueError, match="YAML 解析失败"):
        manager.load()


def test_set_value_simple(tmp_path: Path) -> None:
    """set_value 写入简单键"""
    global_path = tmp_path / "global.yaml"
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    manager.set_value("default_template", "essay")
    data = yaml.safe_load(global_path.read_text(encoding="utf-8"))
    assert data["default_template"] == "essay"


def test_set_value_nested(tmp_path: Path) -> None:
    """set_value 支持点号分隔嵌套键"""
    global_path = tmp_path / "global.yaml"
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    manager.set_value("account.app_id", "wx123")
    data = yaml.safe_load(global_path.read_text(encoding="utf-8"))
    assert data["account"]["app_id"] == "wx123"


def test_set_value_coerce_bool(tmp_path: Path) -> None:
    """set_value 自动转换 bool 字符串"""
    global_path = tmp_path / "global.yaml"
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    manager.set_value("scf.enabled", "true")
    data = yaml.safe_load(global_path.read_text(encoding="utf-8"))
    assert data["scf"]["enabled"] is True

    manager.set_value("scf.enabled", "false")
    data = yaml.safe_load(global_path.read_text(encoding="utf-8"))
    assert data["scf"]["enabled"] is False


def test_set_value_coerce_int(tmp_path: Path) -> None:
    """set_value 自动转换整数"""
    global_path = tmp_path / "global.yaml"
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    manager.set_value("preview.port", "8888")
    data = yaml.safe_load(global_path.read_text(encoding="utf-8"))
    assert data["preview"]["port"] == 8888


def test_set_value_empty_key(tmp_path: Path) -> None:
    """空键抛 ValueError"""
    manager = ConfigManager(
        global_config_path=tmp_path / "global.yaml",
        project_config_path=tmp_path / "project.yaml",
    )
    with pytest.raises(ValueError, match="配置键不能为空"):
        manager.set_value("", "value")


def test_set_value_invalid_key_format(tmp_path: Path) -> None:
    """键格式非法(含空段)抛 ValueError"""
    global_path = tmp_path / "global.yaml"
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    with pytest.raises(ValueError, match="配置键格式非法"):
        manager.set_value("account..app_id", "x")


def test_get_value_simple(tmp_path: Path) -> None:
    """get_value 读取简单键"""
    global_path = tmp_path / "global.yaml"
    global_path.write_text("default_template: essay\n", encoding="utf-8")
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    assert manager.get_value("default_template") == "essay"


def test_get_value_nested(tmp_path: Path) -> None:
    """get_value 读取嵌套键"""
    global_path = tmp_path / "global.yaml"
    global_path.write_text(
        "account:\n  app_id: my-id\n  app_secret: secret\n",
        encoding="utf-8",
    )
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    assert manager.get_value("account.app_id") == "my-id"
    assert manager.get_value("account.app_secret") == "secret"


def test_get_value_missing_key(tmp_path: Path) -> None:
    """get_value 不存在的键返回 None"""
    manager = ConfigManager(
        global_config_path=tmp_path / "global.yaml",
        project_config_path=tmp_path / "project.yaml",
    )
    assert manager.get_value("nonexistent.key") is None


def test_init_config_global(tmp_path: Path, monkeypatch) -> None:
    """init_config 创建全局配置文件(从示例复制)"""
    global_path = tmp_path / "global.yaml"
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    # 找到示例配置文件
    example_path = (
        Path(__file__).resolve().parents[2] / ".aap" / "config.example.yaml"
    )
    if not example_path.exists():
        pytest.skip("示例配置文件不存在")

    created = manager.init_config(target="global")
    assert created.exists()
    assert created == global_path
    # 内容应包含关键字段
    text = created.read_text(encoding="utf-8")
    assert "account" in text
    assert "scf" in text


def test_init_config_already_exists(tmp_path: Path) -> None:
    """配置文件已存在时抛 FileExistsError"""
    global_path = tmp_path / "global.yaml"
    global_path.write_text("existing", encoding="utf-8")
    manager = ConfigManager(
        global_config_path=global_path,
        project_config_path=tmp_path / "project.yaml",
    )
    with pytest.raises(FileExistsError):
        manager.init_config(target="global")


def test_deep_merge() -> None:
    """_deep_merge 递归合并字典"""
    manager = ConfigManager(
        global_config_path=Path("/tmp/x"),
        project_config_path=Path("/tmp/y"),
    )
    base = {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}
    overlay = {"b": {"y": 20, "z": 30}, "d": 4}
    result = manager._deep_merge(base, overlay)
    assert result == {
        "a": 1,
        "b": {"x": 1, "y": 20, "z": 30},
        "c": 3,
        "d": 4,
    }


def test_coerce_value() -> None:
    """_coerce_value 自动转换类型"""
    manager = ConfigManager(
        global_config_path=Path("/tmp/x"),
        project_config_path=Path("/tmp/y"),
    )
    assert manager._coerce_value("true") is True
    assert manager._coerce_value("yes") is True
    assert manager._coerce_value("on") is True
    assert manager._coerce_value("false") is False
    assert manager._coerce_value("no") is False
    assert manager._coerce_value("off") is False
    assert manager._coerce_value("123") == 123
    assert manager._coerce_value("3.14") == 3.14
    assert manager._coerce_value("plain text") == "plain text"
