from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

INTERCEPTION_MIRROR_URL = "https://ghproxy.net/https://github.com/oblitum/Interception/releases/download/v1.0.1/Interception.zip"
INTERCEPTION_ZIP_URL = "https://github.com/oblitum/Interception/releases/download/v1.0.1/Interception.zip"


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

    work_dir = Path(__file__).resolve().parent / "debug" / "interception_setup"
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / "Interception.zip"

    print("\n正在下载 Interception 驱动安装包...")
    download_success = False
    for url in [INTERCEPTION_MIRROR_URL, INTERCEPTION_ZIP_URL]:
        try:
            print(f"正在从以下地址下载: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp, open(zip_path, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)
            download_success = True
            print("下载成功！")
            break
        except Exception as error:
            print(f"该地址下载失败或超时: {error}")

    if not download_success or not zip_path.exists():
        print("\n[错误] 自动下载失败（网络原因无法连接 GitHub）。")
        print("请按以下步骤手动安装：")
        print("1. 浏览器打开: https://github.com/oblitum/Interception/releases")
        print("2. 下载 Interception.zip 并解压。")
        print("3. 以管理员身份运行 CMD，进入解压目录中的 'command line installer' 文件夹。")
        print("4. 执行命令: install-interception.exe /install")
        print("5. 重启电脑。\n")
        return 2

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
        print("请保存好其他工作，重启电脑后运行 start.bat 即可体验驱动级点击！")
        print("========================================================\n")
        return 0
    else:
        print(f"\n[提示] 安装返回码为 {proc.returncode}，请检查上方日志。")
        return 4


if __name__ == "__main__":
    sys.exit(main())
