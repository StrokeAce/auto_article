"""pytest 测试夹具"""
from pathlib import Path

import pytest


@pytest.fixture
def sample_md_path() -> Path:
    """返回测试用 Markdown 文件路径"""
    return Path(__file__).parent / "fixtures" / "minimal" / "sample.md"
