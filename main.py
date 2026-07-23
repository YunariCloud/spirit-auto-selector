from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import ImageGrab


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CONFIG_PATH = ROOT / "config.json"
DEBUG_DIR = ROOT / "debug"

VK_ESCAPE = 0x1B
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class INPUT_VALUE(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT),)


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = (("type", wintypes.DWORD), ("value", INPUT_VALUE))


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass(frozen=True)
class SpriteDefinition:
    id: str
    name: str
    unselected: str
    selected: str
    unselected_threshold: float
    selected_threshold: float


@dataclass(frozen=True)
class SpriteTemplate:
    definition: SpriteDefinition
    unselected_image: np.ndarray
    selected_image: np.ndarray
    unselected_mask: np.ndarray
    selected_mask: np.ndarray


@dataclass(frozen=True)
class SpriteMatch:
    sprite: SpriteTemplate
    match: Match


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_image(name: str) -> np.ndarray:
    path = ASSETS / name
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"无法读取模板：{path}")
    return image


def get_sprite_definitions(config: dict) -> list[SpriteDefinition]:
    """Read the extensible sprite list, with compatibility for old configs."""
    raw_sprites = config.get("sprites")
    if not raw_sprites:
        raw_sprites = [
            {
                "id": "default",
                "name": "当前精灵",
                "unselected": "unselected.png",
                "selected": "selected.png",
            }
        ]

    definitions: list[SpriteDefinition] = []
    seen_ids: set[str] = set()
    global_thresholds = config.get("thresholds", {})
    for index, item in enumerate(raw_sprites, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"第 {index} 个精灵配置不是对象")
        sprite_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not sprite_id or not name:
            raise RuntimeError(f"第 {index} 个精灵配置缺少 id 或 name")
        if sprite_id in seen_ids:
            raise RuntimeError(f"精灵 id 重复：{sprite_id}")
        seen_ids.add(sprite_id)
        thresholds = item.get("thresholds", {})
        definitions.append(
            SpriteDefinition(
                id=sprite_id,
                name=name,
                unselected=str(item.get("unselected", "")).strip(),
                selected=str(item.get("selected", "")).strip(),
                unselected_threshold=float(
                    thresholds.get("unselected", global_thresholds.get("unselected", 0.86))
                ),
                selected_threshold=float(
                    thresholds.get("selected", global_thresholds.get("selected", 0.80))
                ),
            )
        )
    return definitions


def selected_sprite_ids(config: dict, requested: list[str] | None = None) -> list[str]:
    definitions = get_sprite_definitions(config)
    known = {item.id for item in definitions}
    selected = requested if requested is not None else config.get("default_sprites", [definitions[0].id])
    selected = [str(item) for item in selected]
    unknown = [item for item in selected if item not in known]
    if unknown:
        raise RuntimeError(f"未知精灵：{', '.join(unknown)}")
    if not selected:
        raise RuntimeError("请至少选择一种精灵")
    return list(dict.fromkeys(selected))


def load_sprite_templates(config: dict, requested: list[str] | None = None) -> list[SpriteTemplate]:
    wanted = set(selected_sprite_ids(config, requested))
    templates: list[SpriteTemplate] = []
    for definition in get_sprite_definitions(config):
        if definition.id not in wanted:
            continue
        if not definition.unselected or not definition.selected:
            raise RuntimeError(f"精灵“{definition.name}”缺少模板文件配置")
        unselected = load_image(definition.unselected)
        selected = load_image(definition.selected)
        templates.append(
            SpriteTemplate(
                definition=definition,
                unselected_image=unselected,
                selected_image=selected,
                unselected_mask=make_card_mask(unselected),
                selected_mask=make_card_mask(selected),
            )
        )
    return templates


def window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    if not hwnd:
        return "（无标题窗口）"
    length = int(user32.GetWindowTextLengthW(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value or "（无标题窗口）"


def foreground_window() -> tuple[int, str]:
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    if not hwnd:
        raise RuntimeError("无法获取当前前台窗口")
    return hwnd, window_title(hwnd)


def capture_window(hwnd: int) -> tuple[np.ndarray, tuple[int, int]]:
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        raise RuntimeError("目标窗口已经最小化，请先恢复窗口")
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("无法读取目标窗口的客户区")
    top_left = wintypes.POINT(rect.left, rect.top)
    bottom_right = wintypes.POINT(rect.right, rect.bottom)
    if not user32.ClientToScreen(hwnd, ctypes.byref(top_left)) or not user32.ClientToScreen(
        hwnd, ctypes.byref(bottom_right)
    ):
        raise RuntimeError("无法确定目标窗口的屏幕位置")
    if bottom_right.x - top_left.x < 100 or bottom_right.y - top_left.y < 100:
        raise RuntimeError("目标窗口客户区尺寸过小")
    image = ImageGrab.grab(
        bbox=(top_left.x, top_left.y, bottom_right.x, bottom_right.y),
        all_screens=True,
    )
    rgb = np.asarray(image)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr, (top_left.x, top_left.y)


def activate_window(hwnd: int) -> None:
    """Bring the selected window forward so screen capture cannot include an overlay."""
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)


def escape_pressed() -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


class MouseClicker:
    """Handles mouse click operations using Interception driver or SendInput."""

    def __init__(self, mode: str = "interception", fallback_on_missing: bool = True) -> None:
        self.requested_mode = mode.lower()
        self.fallback_on_missing = fallback_on_missing
        self.active_mode = "send_input"
        self._interception = None

        if self.requested_mode == "interception":
            try:
                import interception

                self._interception = interception
                try:
                    interception.auto_capture_devices(keyboard=False, mouse=True)
                except Exception:
                    pass
                self.active_mode = "interception"
                print("输入模式：Interception 驱动级鼠标输入")
            except Exception as error:
                err_msg = (
                    f"初始化 Interception 驱动失败 ({error})。\n"
                    "提示：请确保已在 Windows 系统中安装 Interception 驱动 (interception.sys)。\n"
                    "安装步骤：下载 Interception 安装包，以管理员身份运行 install-interception.exe /install 并重启电脑。"
                )
                if self.fallback_on_missing:
                    print(f"警告：{err_msg}")
                    print("已自动降级为 Windows SendInput 模式。\n")
                    self.active_mode = "send_input"
                else:
                    raise RuntimeError(
                        f"{err_msg}\n（如需允许自动降级，请在 config.json 中设置 fallback_on_driver_missing: true）"
                    ) from error
        else:
            self.active_mode = "send_input"
            print("输入模式：Windows SendInput 模式")

    def click(self, hwnd: int, x: int, y: int) -> None:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

        if self.active_mode == "interception" and self._interception is not None:
            user32.SetCursorPos(int(x), int(y))
            time.sleep(0.02)
            try:
                self._interception.move_to(int(x), int(y))
                time.sleep(0.02)
                self._interception.mouse_down("left")
                time.sleep(0.03)
                self._interception.mouse_up("left")
                return
            except Exception as error:
                print(f"警告：Interception 驱动点击发生异常 ({error})，降级使用 SendInput。")

        if not user32.SetCursorPos(int(x), int(y)):
            raise RuntimeError("无法移动鼠标指针")
        time.sleep(0.04)
        inputs = (INPUT * 2)(
            INPUT(type=0, mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN)),
            INPUT(type=0, mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP)),
        )
        sent = int(user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT)))
        if sent != 2:
            raise RuntimeError(f"Windows SendInput 只发送了 {sent}/2 个鼠标事件")


def click_screen(hwnd: int, x: int, y: int, clicker: MouseClicker | None = None) -> None:
    if clicker is not None:
        clicker.click(hwnd, x, y)
    else:
        MouseClicker(mode="send_input").click(hwnd, x, y)


def check_failsafe(stop_event: threading.Event | None = None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise KeyboardInterrupt
    if escape_pressed():
        raise KeyboardInterrupt
    user32 = ctypes.windll.user32
    virtual_origin = (
        int(user32.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
        int(user32.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
    )
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    if point.x <= virtual_origin[0] + 2 and point.y <= virtual_origin[1] + 2:
        raise KeyboardInterrupt


def make_card_mask(template: np.ndarray) -> np.ndarray:
    """Ignore the changing quantity printed in the lower-right corner."""
    height, width = template.shape[:2]
    mask = np.full((height, width), 255, dtype=np.uint8)
    mask[int(height * 0.68) : height, int(width * 0.59) : width] = 0
    # Avoid letting a large uniform corner dominate the score.
    mask[:3, :] = 0
    mask[-3:, :] = 0
    mask[:, :3] = 0
    mask[:, -3:] = 0
    return mask


def find_matches(
    screen: np.ndarray,
    template: np.ndarray,
    threshold: float,
    mask: np.ndarray | None = None,
    min_distance: float = 0.55,
) -> list[Match]:
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    height, width = template_gray.shape
    if screen_gray.shape[0] < height or screen_gray.shape[1] < width:
        return []

    if mask is None:
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    else:
        result = cv2.matchTemplate(
            screen_gray,
            template_gray,
            cv2.TM_CCOEFF_NORMED,
            mask=mask,
        )

    # Masked correlation can produce NaN/Inf on nearly uniform regions. More
    # importantly, every pixel around one good match can exceed the threshold;
    # feeding all of them into pairwise NMS is extremely slow on a large window.
    result = np.nan_to_num(result, nan=-1.0, posinf=-1.0, neginf=-1.0)
    peak_kernel = np.ones((7, 7), dtype=np.uint8)
    local_max = cv2.dilate(result, peak_kernel)
    ys, xs = np.where((result >= threshold) & (result >= local_max - 1e-7))

    # A normal backpack page only contains a small number of cards. This cap
    # prevents an unusual background from causing quadratic work in NMS.
    max_candidates = 500
    if len(xs) > max_candidates:
        scores = result[ys, xs]
        top = np.argpartition(scores, -max_candidates)[-max_candidates:]
        ys = ys[top]
        xs = xs[top]
    candidates = sorted(
        (
            Match(int(x), int(y), width, height, float(result[y, x]))
            for y, x in zip(ys, xs)
        ),
        key=lambda item: item.score,
        reverse=True,
    )

    kept: list[Match] = []
    distance_limit = min(width, height) * min_distance
    for candidate in candidates:
        cx, cy = candidate.center
        if all((cx - k.center[0]) ** 2 + (cy - k.center[1]) ** 2 >= distance_limit**2 for k in kept):
            kept.append(candidate)
    return kept


def find_sprite_matches(screen: np.ndarray, sprites: list[SpriteTemplate]) -> list[SpriteMatch]:
    """Find every requested sprite type and merge duplicate card detections."""
    candidates: list[SpriteMatch] = []
    for sprite in sprites:
        matches = find_matches(
            screen,
            sprite.unselected_image,
            sprite.definition.unselected_threshold,
            mask=sprite.unselected_mask,
        )
        candidates.extend(SpriteMatch(sprite, match) for match in matches)

    candidates.sort(key=lambda item: item.match.score, reverse=True)
    kept: list[SpriteMatch] = []
    for candidate in candidates:
        cx, cy = candidate.match.center
        duplicate = False
        for existing in kept:
            ex, ey = existing.match.center
            distance_limit = min(
                candidate.match.width,
                candidate.match.height,
                existing.match.width,
                existing.match.height,
            ) * 0.45
            if (cx - ex) ** 2 + (cy - ey) ** 2 < distance_limit**2:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def verify_selected_nearby(
    screen: np.ndarray,
    target: Match,
    selected_template: np.ndarray,
    selected_mask: np.ndarray,
    threshold: float,
) -> bool:
    """Verify only around the clicked card instead of scanning the full window."""
    margin = 45
    screen_height, screen_width = screen.shape[:2]
    left = max(0, target.x - margin)
    top = max(0, target.y - margin)
    right = min(screen_width, target.x + target.width + margin)
    bottom = min(screen_height, target.y + target.height + margin)
    nearby_screen = screen[top:bottom, left:right]
    matches = find_matches(
        nearby_screen,
        selected_template,
        threshold,
        mask=selected_mask,
    )
    target_x, target_y = target.center
    return any(
        abs((item.center[0] + left) - target_x) <= 35
        and abs((item.center[1] + top) - target_y) <= 35
        for item in matches
    )


def yellow_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return cv2.inRange(
        hsv,
        np.array([8, 80, 145], dtype=np.uint8),
        np.array([45, 255, 255], dtype=np.uint8),
    )


def glyphs_from_mask(mask: np.ndarray) -> list[np.ndarray]:
    active_columns = np.any(mask > 0, axis=0)
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(active_columns):
        if active and start is None:
            start = index
        if start is not None and (not active or index == len(active_columns) - 1):
            end = index if not active else index + 1
            if end - start >= 2:
                spans.append((start, end))
            start = None

    glyphs: list[np.ndarray] = []
    for left, right in spans:
        crop = mask[:, left:right]
        active_rows = np.any(crop > 0, axis=1)
        rows = np.flatnonzero(active_rows)
        if rows.size:
            glyphs.append(crop[rows[0] : rows[-1] + 1])
    return glyphs


def normalize_glyph(glyph: np.ndarray, size: tuple[int, int] = (24, 32)) -> np.ndarray:
    canvas = np.zeros((size[1], size[0]), dtype=np.uint8)
    height, width = glyph.shape
    scale = min((size[0] - 4) / max(width, 1), (size[1] - 4) / max(height, 1))
    resized = cv2.resize(
        glyph,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_NEAREST,
    )
    y = (canvas.shape[0] - resized.shape[0]) // 2
    x = (canvas.shape[1] - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def glyph_similarity(left: np.ndarray, right: np.ndarray) -> float:
    a = normalize_glyph(left) > 0
    b = normalize_glyph(right) > 0
    union = np.logical_or(a, b).sum()
    if not union:
        return 0.0
    return float(np.logical_and(a, b).sum() / union)


class PageDetector:
    """Find the page label and compare the glyphs on both sides of '/'."""

    def __init__(self, reference: np.ndarray, anchor_threshold: float) -> None:
        self.reference = reference
        # Stable text: "筛选中". Digits are deliberately excluded.
        self.anchor_rect = (24, 15, 101, 38)
        x, y, width, height = self.anchor_rect
        self.anchor = reference[y : y + height, x : x + width]
        self.anchor_threshold = anchor_threshold
        reference_number_mask = yellow_mask(reference[15:52, 125:195])
        glyphs = glyphs_from_mask(reference_number_mask)
        if len(glyphs) != 3:
            raise RuntimeError("分页模板格式异常，应类似于“筛选中 1/1”")
        self.slash_glyph = glyphs[1]

    def inspect(self, screen: np.ndarray) -> tuple[bool | None, float, list[float]]:
        matches = find_matches(screen, self.anchor, self.anchor_threshold)
        if not matches:
            return None, 0.0, []
        anchor_match = matches[0]
        ref_x, ref_y, _, _ = self.anchor_rect
        label_x = anchor_match.x - ref_x
        label_y = anchor_match.y - ref_y

        height, width = screen.shape[:2]
        left = max(0, label_x + 125)
        top = max(0, label_y + 15)
        right = min(width, label_x + 280)
        bottom = min(height, label_y + 52)
        if right <= left or bottom <= top:
            return None, anchor_match.score, []

        glyphs = glyphs_from_mask(yellow_mask(screen[top:bottom, left:right]))
        slash_scores = [glyph_similarity(glyph, self.slash_glyph) for glyph in glyphs]
        if not slash_scores or max(slash_scores) < 0.62:
            return None, anchor_match.score, slash_scores
        slash_index = int(np.argmax(slash_scores))
        current = glyphs[:slash_index]
        total = glyphs[slash_index + 1 :]
        if not current or len(current) != len(total):
            return False, anchor_match.score, slash_scores
        digit_scores = [glyph_similarity(a, b) for a, b in zip(current, total)]
        return all(score >= 0.78 for score in digit_scores), anchor_match.score, digit_scores


def screen_changed(before: np.ndarray, after: np.ndarray, threshold: float) -> bool:
    if before.shape != after.shape:
        return True
    small_before = cv2.resize(before, (320, 180), interpolation=cv2.INTER_AREA)
    small_after = cv2.resize(after, (320, 180), interpolation=cv2.INTER_AREA)
    difference = float(cv2.absdiff(small_before, small_after).mean())
    return difference >= threshold


def make_debug_image(screen: np.ndarray, matches: list[Match]) -> np.ndarray:
    annotated = screen.copy()
    for match in matches:
        cv2.rectangle(
            annotated,
            (match.x, match.y),
            (match.x + match.width, match.y + match.height),
            (0, 0, 255),
            2,
        )
        cv2.putText(
            annotated,
            f"{match.score:.3f}",
            (match.x, max(15, match.y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )
    return annotated


def save_debug(screen: np.ndarray, matches: list[Match], label: str) -> Path:
    DEBUG_DIR.mkdir(exist_ok=True)
    annotated = make_debug_image(screen, matches)
    path = DEBUG_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.png"
    cv2.imencode(".png", annotated)[1].tofile(path)
    return path


def run(
    dry_run: bool = False,
    sprite_ids: list[str] | None = None,
    target_hwnd: int | None = None,
    stop_event: threading.Event | None = None,
    debug_callback: Callable[[np.ndarray, str], None] | None = None,
) -> int:
    config = load_config()
    next_template = load_image("next_page.png")
    # The supplied crop contains a yellow strip on its right/bottom edge which
    # is not part of the button. Use only the stable circular button area.
    next_template = next_template[7:76, 3:76]
    pagination_template = load_image("pagination.png")
    sprites = load_sprite_templates(config, sprite_ids)
    page_detector = PageDetector(
        pagination_template,
        float(config["thresholds"]["pagination_anchor"]),
    )

    print("请把游戏背包页完整显示在屏幕上，并保持窗口无遮挡。")
    print("运行中按 Esc，或把鼠标快速移到整个桌面的左上角，可立即停止。")
    print("本次选择：" + "、".join(sprite.definition.name for sprite in sprites))
    if dry_run:
        print("当前为检测模式：只截图识别，不会点击。")
    if target_hwnd is None:
        for remaining in range(int(config["startup_countdown"]), 0, -1):
            check_failsafe(stop_event)
            print(f"请切换到游戏窗口，{remaining} 秒后锁定当前窗口……")
            time.sleep(1)
        hwnd, target_title = foreground_window()
    else:
        hwnd = int(target_hwnd)
        target_title = window_title(hwnd)
    print(f"已锁定目标窗口：{target_title}")
    activate_window(hwnd)
    time.sleep(0.25)

    clicker = None
    if not dry_run:
        clicker = MouseClicker(
            mode=str(config.get("input_mode", "interception")),
            fallback_on_missing=bool(config.get("fallback_on_driver_missing", True)),
        )

    pages_visited = 0
    total_selected = 0
    stale_next_attempts = 0

    while pages_visited < int(config["max_pages"]):
        screen, origin = capture_window(hwnd)
        check_failsafe(stop_event)
        pages_visited += 1

        print(f"第 {pages_visited} 个页面：正在识别目标……", flush=True)
        recognition_started = time.perf_counter()
        sprite_matches = find_sprite_matches(screen, sprites)
        matches = [item.match for item in sprite_matches]
        print("  正在识别分页……", flush=True)
        last_page, anchor_score, digit_scores = page_detector.inspect(screen)
        recognition_seconds = time.perf_counter() - recognition_started
        print(
            f"第 {pages_visited} 个页面：发现 {len(matches)} 个未选中目标；"
            f"分页={'最后一页' if last_page else '非末页' if last_page is False else '未识别'} "
            f"(锚点 {anchor_score:.3f}, 数字 {digit_scores})；"
            f"识别耗时 {recognition_seconds:.2f} 秒",
            flush=True,
        )
        if sprite_matches:
            counts: dict[str, int] = {}
            for item in sprite_matches:
                counts[item.sprite.definition.name] = counts.get(item.sprite.definition.name, 0) + 1
            print("  分类：" + "，".join(f"{name} {count} 个" for name, count in counts.items()))

        if dry_run:
            next_matches = find_matches(
                screen,
                next_template,
                float(config["thresholds"]["next_page"]),
            )
            debug_matches = matches + next_matches
            if debug_callback is not None:
                debug_callback(make_debug_image(screen, debug_matches), "检测结果")
                print("检测图已在界面中显示，不会保存到磁盘。")
            else:
                output = save_debug(screen, debug_matches, "dry-run")
                print(f"检测图已保存：{output}")
            return 0 if matches and next_matches else 2

        for index, detected in enumerate(sprite_matches, start=1):
            check_failsafe(stop_event)
            match = detected.match
            local_x, local_y = match.center
            click_screen(hwnd, origin[0] + local_x, origin[1] + local_y, clicker=clicker)
            total_selected += 1
            print(
                f"  已点击 {detected.sprite.definition.name} {index}/{len(matches)}，"
                f"位置 ({local_x}, {local_y})"
            )
            time.sleep(float(config["delays"]["after_select"]))

            # A selected match is only a confidence signal; no extra click is made on failure.
            verify_screen, _ = capture_window(hwnd)
            nearby = verify_selected_nearby(
                verify_screen,
                match,
                detected.sprite.selected_image,
                detected.sprite.selected_mask,
                detected.sprite.definition.selected_threshold,
            )
            if not nearby:
                print("    提示：未看到对应的已选中模板；将继续运行，结束后请抽查结果。")

        # Re-capture because clicking targets changes the screen.
        screen, origin = capture_window(hwnd)
        last_page, _, _ = page_detector.inspect(screen)
        if last_page is True:
            print(f"完成：最后一页已处理，共点击 {total_selected} 个目标。")
            return 0

        next_matches = find_matches(
            screen,
            next_template,
            float(config["thresholds"]["next_page"]),
        )
        if not next_matches:
            if debug_callback is not None:
                debug_callback(make_debug_image(screen, matches), "未找到下一页按钮")
                print("未找到下一页按钮，已安全停止；诊断图仅在界面中显示。")
            else:
                output = save_debug(screen, matches, "next-not-found")
                print(f"未找到下一页按钮，已安全停止。诊断图：{output}")
            return 3

        next_match = next_matches[0]
        before = screen
        nx, ny = next_match.center
        click_screen(hwnd, origin[0] + nx, origin[1] + ny, clicker=clicker)
        time.sleep(float(config["delays"]["after_page_turn"]))
        after, _ = capture_window(hwnd)
        if screen_changed(before, after, float(config["page_change_threshold"])):
            stale_next_attempts = 0
        else:
            stale_next_attempts += 1
            print(f"下一页点击后画面未变化（{stale_next_attempts}/2）。")
            if stale_next_attempts >= 2:
                print(f"画面连续两次未变化，视为已经到底。共点击 {total_selected} 个目标。")
                return 0

    print(f"达到安全页数上限 {config['max_pages']}，已停止。共点击 {total_selected} 个目标。")
    return 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按图片模板选择背包精灵并自动翻页")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只识别并输出诊断截图，不执行点击",
    )
    parser.add_argument(
        "--sprites",
        help="要处理的精灵 id，多个 id 使用英文逗号分隔；默认读取 config.json",
    )
    parser.add_argument(
        "--list-sprites",
        action="store_true",
        help="列出可用精灵并退出",
    )
    return parser.parse_args()


if __name__ == "__main__":
    enable_dpi_awareness()
    try:
        args = parse_args()
        if args.list_sprites:
            config = load_config()
            defaults = set(selected_sprite_ids(config))
            for sprite in get_sprite_definitions(config):
                marker = "*" if sprite.id in defaults else " "
                print(f"{marker} {sprite.id}: {sprite.name}")
            raise SystemExit(0)
        requested_sprites = None
        if args.sprites:
            requested_sprites = [item.strip() for item in args.sprites.split(",") if item.strip()]
        raise SystemExit(run(args.dry_run, sprite_ids=requested_sprites))
    except KeyboardInterrupt:
        print("\n已由用户紧急停止。")
        raise SystemExit(130)
    except Exception as error:
        print(f"\n运行失败：{error}", file=sys.stderr)
        raise SystemExit(1)
