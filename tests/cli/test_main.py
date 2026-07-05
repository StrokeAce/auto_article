"""CLI 主入口测试"""
from typer.testing import CliRunner

from aap.cli.main import app

runner = CliRunner()


def test_help() -> None:
    """测试 --help 命令可正常运行"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AAP" in result.output or "aap" in result.output.lower()
