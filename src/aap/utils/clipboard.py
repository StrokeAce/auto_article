"""剪贴板工具

跨平台将文本复制到系统剪贴板。
优先使用系统命令(无依赖),失败则尝试 pyperclip(需安装)。
"""
from __future__ import annotations

import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> bool:
    """复制文本到系统剪贴板

    Args:
        text: 待复制文本

    Returns:
        是否复制成功
    """
    if not text:
        return False

    # 1. 尝试 pyperclip(若已安装)
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        pass
    except Exception:
        pass

    # 2. 平台特定命令
    if sys.platform == "win32":
        return _copy_windows(text)
    elif sys.platform == "darwin":
        return _copy_macos(text)
    else:
        return _copy_linux(text)


def _copy_windows(text: str) -> bool:
    """Windows: 使用 PowerShell Set-Clipboard"""
    try:
        # 用 PowerShell 设置剪贴板,UTF-8 编码避免中文乱码
        ps_script = (
            "$OutputEncoding = [System.Text.Encoding]::UTF8; "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Set-Clipboard -Value @\"\n"
            f"{text}\n"
            "\"@"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        # 降级:用 clip 命令(可能中文乱码)
        try:
            if shutil.which("clip"):
                proc = subprocess.run(
                    ["clip"],
                    input=text.encode("utf-16-le"),
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return proc.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return False


def _copy_macos(text: str) -> bool:
    """macOS: 使用 pbcopy"""
    try:
        if shutil.which("pbcopy"):
            subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=5,
            )
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return False


def _copy_linux(text: str) -> bool:
    """Linux: 优先 xclip,其次 xsel"""
    # xclip
    try:
        if shutil.which("xclip"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=5,
            )
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # xsel
    try:
        if shutil.which("xsel"):
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=5,
            )
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return False
