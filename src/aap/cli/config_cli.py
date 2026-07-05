"""aap config init/set/get 命令

初始化或修改 AAP 配置。
"""
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="初始化或修改配置")


@app.command("init")
def init_config(
    target: str = typer.Option(
        "global",
        "--target",
        "-t",
        help="配置目标: global(~/.aap/config.yaml) 或 project(./.aap/config.yaml)",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已存在的配置文件"),
) -> None:
    """初始化配置文件(从示例复制)"""
    from aap.config.manager import ConfigManager

    if target not in ("global", "project"):
        typer.echo(f"错误: target 必须为 global 或 project,当前: {target}", err=True)
        raise typer.Exit(1)

    manager = ConfigManager()

    if force:
        # 强制覆盖:先删除已存在的目标文件
        target_path = manager.global_path if target == "global" else manager.project_path
        if target_path.exists():
            target_path.unlink()

    try:
        path = manager.init_config(target=target)
    except FileExistsError as e:
        typer.echo(f"错误: {e}", err=True)
        typer.echo("提示: 使用 --force 覆盖已存在的文件", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"配置已创建: {path}")
    typer.echo("请编辑该文件,填入真实的 AppID/AppSecret 等信息")


@app.command("set")
def set_value(
    key: str = typer.Argument(..., help="配置键,如 account.app_id"),
    value: str = typer.Argument(..., help="配置值"),
) -> None:
    """修改配置项(支持点号分隔的键)"""
    from aap.config.manager import ConfigManager

    manager = ConfigManager()
    try:
        manager.set_value(key, value)
    except ValueError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"已设置 {key} = {value}")


@app.command("get")
def get_value(
    key: str = typer.Argument(..., help="配置键,如 account.app_id"),
) -> None:
    """读取配置项"""
    from aap.config.manager import ConfigManager

    manager = ConfigManager()
    try:
        value = manager.get_value(key)
    except ValueError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)

    if value is None:
        typer.echo(f"(未设置) {key}")
    else:
        # 隐藏敏感字段的部分内容
        if isinstance(value, str) and any(
            s in key.lower() for s in ("secret", "password", "token")
        ) and len(value) > 6:
            masked = value[:3] + "***" + value[-3:]
            typer.echo(f"{key} = {masked}")
        else:
            typer.echo(f"{key} = {value}")


@app.command("show")
def show_config() -> None:
    """显示当前生效的配置(敏感字段已脱敏)"""
    from aap.config.manager import ConfigManager

    manager = ConfigManager()
    try:
        config = manager.load()
    except ValueError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)

    def _mask(key: str, value: str) -> str:
        if isinstance(value, str) and any(
            s in key.lower() for s in ("secret", "password", "token")
        ) and len(value) > 6:
            return value[:3] + "***" + value[-3:]
        return str(value)

    typer.echo(f"account.app_id     = {config.account.app_id}")
    typer.echo(f"account.app_secret = {_mask('secret', config.account.app_secret)}")
    typer.echo(f"account.nickname   = {config.account.nickname}")
    typer.echo(f"scf.url            = {config.scf.url}")
    typer.echo(f"scf.secret         = {_mask('secret', config.scf.secret)}")
    typer.echo(f"scf.enabled        = {config.scf.enabled}")
    typer.echo(f"default_template   = {config.default_template}")
    typer.echo(f"preview.port       = {config.preview.port}")
    typer.echo(f"preview.default_mode = {config.preview.default_mode}")
    typer.echo(f"publish.output_dir = {config.publish.output_dir}")
    typer.echo(f"history.enabled    = {config.history.enabled}")
