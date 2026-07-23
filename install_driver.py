from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

INTERCEPTION_ZIP_URL = "https://github.com/oblitum/Interception/releases/download/v1.0.1/Interception.zip"
INTERCEPTION_ZIP_SHA256 = "AD038963D6413055765128B0B931F6E765147C9916DBA79E65D872B261F9AF10"

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_SHOWNORMAL = 1
INFINITE = 0xFFFFFFFF
ERROR_CANCELLED = 1223


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    )


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def is_interception_installed() -> bool:
    try:
        res = subprocess.run(
            ["sc", "query", "interception"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="ignore",
        )
        return "RUNNING" in res.stdout or "STOPPED" in res.stdout or "STATE" in res.stdout
    except Exception:
        return False


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SpiritAutoSelector"
    return Path(__file__).resolve().parent


def run_elevated_installer() -> int:
    executable = str(Path(sys.executable).resolve())
    if getattr(sys, "frozen", False):
        parameters = "--install-interception-driver"
        working_directory = str(Path(sys.executable).resolve().parent)
    else:
        gui_path = Path(__file__).resolve().with_name("gui.py")
        parameters = f'"{gui_path}" --install-interception-driver'
        working_directory = str(gui_path.parent)

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = parameters
    info.lpDirectory = working_directory
    info.nShow = SW_SHOWNORMAL

    ctypes.set_last_error(0)
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return ctypes.get_last_error() or 1

    try:
        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        exit_code = wintypes.DWORD()
        if not ctypes.windll.kernel32.GetExitCodeProcess(
            info.hProcess, ctypes.byref(exit_code)
        ):
            return ctypes.get_last_error() or 1
        return int(exit_code.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(info.hProcess)


def main() -> int:
    print("=== Interception 驱动自动安装助手 ===")

    if not is_admin():
        print("\n[错误] 安装驱动需要管理员权限！")
        print("请右键以管理员身份运行 CMD/PowerShell 或使用 install-driver.bat。\n")
        return 1

    if is_interception_installed():
        print("\n[提示] 检测到系统已经安装了 Interception 驱动服务！")
        print("如果您之前尚未重启电脑，请重启电脑以使驱动生效。")
        print("如果已重启过，可以直接启动脚本使用。\n")
        return 0

    work_dir = runtime_root() / "debug" / "interception_setup"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / "Interception.zip"

    print("\n正在下载 Interception 驱动安装包...")
    try:
        print(f"正在从 Interception 官方 Release 下载: {INTERCEPTION_ZIP_URL}")
        req = urllib.request.Request(
            INTERCEPTION_ZIP_URL, headers={"User-Agent": "SpiritAutoSelector"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
    except Exception as error:
        print(f"官方下载失败或超时: {error}")

    if not zip_path.exists():
        print("\n[错误] 自动下载失败（网络原因无法连接 GitHub）。")
        print("请按以下步骤手动安装：")
        print("1. 浏览器打开: https://github.com/oblitum/Interception/releases")
        print("2. 下载 Interception.zip 并解压。")
        print("3. 以管理员身份运行 CMD，进入解压目录中的 'command line installer' 文件夹。")
        print("4. 执行命令: install-interception.exe /install")
        print("5. 重启电脑。\n")
        return 2

    actual_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest().upper()
    if actual_hash != INTERCEPTION_ZIP_SHA256:
        zip_path.unlink(missing_ok=True)
        print("\n[错误] Interception 安装包 SHA-256 校验失败，已拒绝安装。")
        print(f"期望: {INTERCEPTION_ZIP_SHA256}")
        print(f"实际: {actual_hash}\n")
        return 5
    print("下载完成，SHA-256 校验通过！")

    print("\n正在解压安装包...")
    extract_dir = work_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    installer_exe = None
    for p in extract_dir.rglob("install-interception.exe"):
        installer_exe = p
        break

    if not installer_exe or not installer_exe.exists():
        print("\n[错误] 解压包中未能定位到 install-interception.exe！")
        return 3

    print(f"定位到安装程序: {installer_exe}")
    print("正在安装内核驱动 (install-interception.exe /install)...")

    proc = subprocess.run(
        [str(installer_exe), "/install"],
        cwd=installer_exe.parent,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="ignore",
    )

    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)

    if proc.returncode == 0 or is_interception_installed() or "Successfully" in proc.stdout:
        print("\n========================================================")
        print("【成功】Interception 驱动已成功完成安装！")
        print("【极其重要】Windows 内核驱动必须在【重启电脑】后才会生效。")
        print("请保存好其他工作，重启电脑后重新运行本工具。")
        print("========================================================\n")
        return 0
    else:
        print(f"\n[提示] 安装返回码为 {proc.returncode}，请检查上方日志。")
        return 4


if __name__ == "__main__":
    sys.exit(main())
