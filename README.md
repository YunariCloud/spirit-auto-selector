# 洛克王国：世界「了不起天分」精灵批量选择工具

用于解决《洛克王国：世界》中“了不起天分”精灵需要一个一个手动点击的问题。工具会自动识别背包里的目标精灵，批量完成点击并自动翻页，直到所有页面处理完成。

> 当前版本只内置了 **噼啪鸟** 一个精灵模板，因为作者目前只截取并测试了这个精灵。其他精灵可以在程序中手动上传截图后进行识别和点击。

## 解决的问题

在游戏背包中筛选“了不起天分”精灵时，玩家原本需要逐个点击每只精灵。这个工具通过图像识别找到尚未选中的目标，一次处理当前页的全部匹配精灵，再自动进入下一页，从而省去重复点击操作。

工具支持一种或多种精灵模板。分页显示中斜杠两侧的数字字形相同时，会在处理完当前页后自动停止。

本程序仅通过截图进行图像识别，并模拟鼠标点击选中精灵，方便玩家后续放生。它不会读取游戏进程内存，不会修改或注入任何游戏数据，也不包含修改游戏客户端的功能。

## 下载 EXE（推荐）

从 GitHub 仓库的 [Releases 页面](https://github.com/YunariCloud/spirit-auto-selector/releases)下载 `SpiritAutoSelector.exe`，双击即可运行，不需要安装 Python。程序启动时会检测 Interception 驱动；若驱动不可用，会阻止进入主界面并通过 Windows 管理员授权自动安装。安装完成后需要重启电脑。

首次运行还会把默认配置和识别模板复制到：

```text
%LOCALAPPDATA%\SpiritAutoSelector
```

此目录中的配置和后来添加的精灵模板会永久保留。若目标游戏以管理员身份运行，请右键 EXE 并选择“以管理员身份运行”。发布版目前没有商业代码签名，Windows 首次启动时可能显示 SmartScreen 提示；请确认文件来自本项目的 GitHub Release。

## 运行环境

- Windows 10 或 Windows 11
- 直接运行 EXE 不需要 Python；从源码运行需要 Python 3.10 或更高版本
- 游戏建议使用窗口化或无边框窗口模式
- 网络连接（首次安装 Python 依赖和 Interception 驱动时需要）

## 使用方法

1. 建议把 Windows 显示缩放和游戏窗口大小保持为截图时的状态。
2. 打开游戏背包页面，确保精灵、分页文字和下一页按钮都没有被其他窗口遮挡。
3. 双击 `SpiritAutoSelector.exe`。若尚未安装 Interception 驱动，请按提示允许管理员权限并完成安装，然后重启电脑。源码模式可继续使用 `start.bat`。
4. 在深色图形界面中选择游戏窗口，勾选需要处理的一种或多种精灵。当前内置模板只有“噼啪鸟”；添加其他精灵后，列表会显示相应缩略图，并可使用名称搜索框实时筛选。
5. 建议先点“仅检测（不点击）”。确认诊断截图正确后，再点“开始自动选择”。运行过程中不要移动或最小化游戏窗口。
6. 随时按 `Esc`、点击界面的“停止”，或把鼠标移到整个桌面的左上角，即可紧急停止。

也可以继续使用原来的命令行检测入口：双击 `detect-only.bat`，或在 PowerShell 中运行：

```powershell
.\test-detection.ps1
```

主界面的检测模式只截取所选窗口的客户区，不包含桌面、其他窗口、标题栏或窗口边框。它不会点击，只会弹出带红框的内存预览；关闭预览后图片立即释放，不会保存到磁盘。红框应同时覆盖目标精灵和下一页按钮。命令行检测入口仍会把诊断图写入 `debug` 文件夹，便于没有图形界面时排查。

## 手动上传其他精灵图片

在主界面中点击“添加精灵模板”，依次填写名称并选择两张模板图片：

- “未选中”模板用于寻找需要点击的卡片。
- “已选中”模板用于点击后的结果校验。

截图不要太大，推荐使用 PixPin 截取精灵卡片中具有辨识度的小范围区域，不要直接上传整张游戏窗口截图。未选中和已选中图片应尽量保持相同的截图范围；截图时的游戏窗口大小和 Windows 显示缩放也应与实际运行时一致。

新模板会复制到 `assets/sprites/<精灵ID>/`，并自动写入 `config.json`。列表中的多种精灵可以同时勾选；若多个模板识别到同一张卡片，只会点击一次。建议先使用“仅检测（不点击）”确认红框位置正确，再执行自动选择。

命令行模式可通过 ID 选择多个精灵：

```powershell
.\.venv\Scripts\python.exe main.py --list-sprites
.\.venv\Scripts\python.exe main.py --sprites default,sprite_12345678
```

## 可调参数

`config.json` 中：

- `input_mode`：固定为 `"interception"`（驱动级模拟点击），其他模式会被拒绝。
- `fallback_on_driver_missing`：固定为 `false`；工具不提供 SendInput 降级方案。
- `default_sprites`：命令行模式默认处理的精灵 ID 列表。
- `sprites`：所有精灵模板配置；每项可分别设置名称、未选中模板、已选中模板和匹配阈值。
- `thresholds.unselected`：未选中精灵匹配阈值。漏识别时可小幅降低，如从 `0.86` 改成 `0.82`；误识别时提高。
- `thresholds.next_page`：下一页按钮匹配阈值。
- `thresholds.pagination_anchor`：分页文字“筛选中”的匹配阈值。
- `delays.after_select`：每次选择后的等待秒数。
- `delays.after_page_turn`：翻页后的等待秒数；游戏加载慢时应增大。
- `max_pages`：异常情况下的安全页数上限。

## Interception 驱动安装说明

工具强制使用 **Interception 驱动级鼠标输入**。启动时会实际尝试连接驱动；驱动未安装或尚未生效时不会进入主界面，也不会降级为 SendInput。

### 方法一：自动安装（推荐）

直接运行 `SpiritAutoSelector.exe`：
1. 工具发现驱动不可用后会提示安装；
2. 确认 Windows 管理员授权；
3. 工具只从 Interception 官方 GitHub Release 下载驱动，并校验安装包 SHA-256；
4. 自动调用 `install-interception.exe /install`；
5. 安装成功后重启电脑，再次运行工具。

源码模式也可以双击项目根目录下的 `install-driver.bat`。

### 方法二：手动安装

1. **下载驱动**：访问 [Interception 官方 Release](https://github.com/oblitum/interception/releases) 下载 `Interception.zip` 安装包。
2. **安装驱动**：解压后，以**管理员身份**打开命令提示符（CMD），进入 `command line installer` 目录并运行：
   ```cmd
   install-interception.exe /install
   ```
3. **重启电脑**：安装成功后重启电脑以生效驱动。

> **注意**：Interception 是必需组件。用户取消管理员授权、安装失败或安装后尚未重启时，工具会退出，不会使用任何降级输入方案。

## 当前模板的适用范围

当前仅提供噼啪鸟模板。未选中模板包含了精灵外观，因此它会寻找与模板中同类、同显示样式的精灵。数量数字区域已被忽略，不同数量不会影响识别。如果需要识别其他精灵，或目标精灵存在明显不同的外观、稀有度边框或尺寸，需要在界面中手动上传相应模板并勾选，才能正确识别。

脚本不会把分页数字转成文本，而是比较 `/` 两侧的字形，所以不依赖 Tesseract 等 OCR 软件。分页识别失败时，还会用连续两次点击“下一页”后画面不变作为到底保护。

## 项目结构

```text
assets/                 图像识别模板
config.json             精灵、阈值、延迟和输入模式配置
gui.py                  图形界面入口
main.py                 截图、识别、翻页和鼠标输入逻辑
start.bat               推荐启动入口
install-driver.bat      Interception 驱动安装入口
detect-only.bat         命令行检测入口
test_logic.py           核心逻辑单元测试
SpiritAutoSelector.spec PyInstaller 单文件构建配置
build.ps1               Windows 一键构建脚本
```

## 开发与测试

安装依赖并执行测试：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v
```

> 自动点击会真实控制鼠标。程序仅负责选中精灵以方便后续放生，不会修改任何游戏数据。调试模板和阈值时请优先使用“仅检测（不点击）”。

构建单文件 EXE：

```powershell
.\build.ps1
```

构建结果位于 `dist\SpiritAutoSelector.exe`。可用以下命令执行不打开界面的资源自检：

```powershell
.\dist\SpiritAutoSelector.exe --smoke-test
```
