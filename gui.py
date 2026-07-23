from __future__ import annotations

import contextlib
import ctypes
from ctypes import wintypes
import io
import json
from pathlib import Path
import queue
import shutil
import sys
import threading
import uuid

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox

import main


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

FONT_FAMILY = "Microsoft YaHei UI"
APP_BG = ("#F3F6FB", "#090D14")
SIDEBAR_BG = ("#111827", "#0D1420")
CARD_BG = ("#FFFFFF", "#111925")
SURFACE_BG = ("#F7F9FC", "#172130")
LOG_BG = ("#F8FAFD", "#080D14")
BORDER = ("#E4E9F2", "#243247")
TEXT = ("#172033", "#ECF2FF")
MUTED = ("#697386", "#8E9BB0")
ACCENT = ("#625BF6", "#7772FF")
ACCENT_HOVER = ("#5048E5", "#8B87FF")
SUCCESS = ("#0C9368", "#39D9A5")


def ui_font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


class QueueWriter(io.TextIOBase):
    def __init__(self, output_queue: queue.Queue) -> None:
        self.output_queue = output_queue

    def write(self, text: str) -> int:
        if text:
            self.output_queue.put(("log", text))
        return len(text)

    def flush(self) -> None:
        pass


def visible_windows() -> list[tuple[int, str]]:
    user32 = ctypes.windll.user32
    results: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        rect = wintypes.RECT()
        if title and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            if rect.right - rect.left >= 300 and rect.bottom - rect.top >= 200:
                results.append((int(hwnd), title))
        return True

    callback_ref = callback_type(callback)
    user32.EnumWindows(callback_ref, 0)
    return results


def valid_image(path: str) -> bool:
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR) is not None
    except Exception:
        return False


class TemplateDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.result: tuple[str, str, str] | None = None
        self.title("添加精灵模板")
        self.geometry("620x390")
        self.configure(fg_color=APP_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.name_var = tk.StringVar()
        self.unselected_var = tk.StringVar()
        self.selected_var = tk.StringVar()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=24)
        ctk.CTkLabel(
            body,
            text="添加精灵模板",
            font=ui_font(22, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text="准备同一只精灵在未选中和已选中状态下的两张截图。",
            font=ui_font(12),
            text_color=MUTED,
        ).pack(anchor="w", pady=(4, 20))

        ctk.CTkLabel(body, text="显示名称", font=ui_font(13, "bold"), text_color=TEXT).pack(anchor="w")
        self.name_entry = ctk.CTkEntry(
            body,
            textvariable=self.name_var,
            height=40,
            corner_radius=10,
            border_color=BORDER,
            fg_color=CARD_BG,
            font=ui_font(),
            placeholder_text="例如：火系精灵",
        )
        self.name_entry.pack(fill="x", pady=(6, 14))
        self._file_row(body, "未选中模板", self.unselected_var)
        self._file_row(body, "已选中模板", self.selected_var)

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", pady=(20, 0))
        ctk.CTkButton(actions, text="取消", width=96, height=40, font=ui_font(13, "bold"), fg_color="transparent", border_width=1, border_color=BORDER, command=self.destroy).pack(side="right")
        ctk.CTkButton(actions, text="添加模板", width=110, height=40, font=ui_font(13, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.submit).pack(side="right", padx=(0, 10))

        self.after(100, self.name_entry.focus_set)

    def _file_row(self, parent: ctk.CTkFrame, label: str, variable: tk.StringVar) -> None:
        ctk.CTkLabel(parent, text=label, font=ui_font(13, "bold"), text_color=TEXT).pack(anchor="w")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(6, 14))
        ctk.CTkEntry(row, textvariable=variable, height=40, corner_radius=10, border_color=BORDER, fg_color=CARD_BG, font=ui_font(12), state="readonly").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="选择图片", width=96, height=40, font=ui_font(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=lambda: self.choose_file(variable)).pack(side="left", padx=(10, 0))

    def choose_file(self, variable: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="选择模板图片",
            filetypes=(("图片文件", "*.png;*.jpg;*.jpeg;*.bmp"), ("所有文件", "*.*")),
        )
        if path:
            variable.set(path)

    def submit(self) -> None:
        name = self.name_var.get().strip()
        unselected = self.unselected_var.get()
        selected = self.selected_var.get()
        if not name or not unselected or not selected:
            messagebox.showwarning("信息不完整", "请填写名称并选择两张模板图片。", parent=self)
            return
        if not valid_image(unselected) or not valid_image(selected):
            messagebox.showerror("模板无效", "选择的文件中有无法读取的图片。", parent=self)
            return
        self.result = (name, unselected, selected)
        self.destroy()


class SpriteApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("精灵批量选择工具")
        self.root.geometry("1100x820")
        self.root.minsize(960, 740)
        self.root.configure(fg_color=APP_BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.config = main.load_config()
        self.enabled_ids = set(main.selected_sprite_ids(self.config))
        self.enabled_vars: dict[str, tk.BooleanVar] = {}
        self.sprite_images: dict[str, ctk.CTkImage] = {}
        self.window_values: dict[str, int] = {}
        self.output_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False

        self._build_ui()
        self.refresh_sprites()
        self.refresh_windows()
        self.root.after(100, self.poll_output)

    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self.root, width=218, corner_radius=0, fg_color=SIDEBAR_BG)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(28, 34))
        ctk.CTkLabel(
            brand,
            text="✦",
            width=42,
            height=42,
            corner_radius=13,
            fg_color=ACCENT,
            text_color="#FFFFFF",
            font=ui_font(20, "bold"),
        ).pack(side="left")
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=(11, 0))
        ctk.CTkLabel(
            brand_text,
            text="SPIRIT  AUTO",
            font=ui_font(9, "bold"),
            text_color=("#9CA3AF", "#8290A6"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_text,
            text="精灵助手",
            font=ui_font(20, "bold"),
            text_color="#F8FAFC",
        ).pack(anchor="w")

        self._step(sidebar, "01", "选择窗口", "锁定游戏画面")
        self._step(sidebar, "02", "选择精灵", "支持同时多选")
        self._step(sidebar, "03", "开始任务", "自动识别与翻页")

        tip = ctk.CTkFrame(sidebar, corner_radius=14, fg_color=("#1D2939", "#151F2D"), border_width=1, border_color=("#344054", "#253247"))
        tip.pack(side="bottom", fill="x", padx=16, pady=18)
        ctk.CTkLabel(tip, text="⌁  安全停止", font=ui_font(12, "bold"), text_color="#F8FAFC").pack(anchor="w", padx=14, pady=(13, 2))
        ctk.CTkLabel(
            tip,
            text="按 Esc 或将鼠标移动到\n屏幕左上角。",
            justify="left",
            font=ui_font(11),
            text_color="#98A2B3",
        ).pack(anchor="w", padx=14, pady=(0, 13))

        main_panel = ctk.CTkFrame(self.root, fg_color="transparent")
        main_panel.grid(row=0, column=1, sticky="nsew", padx=30, pady=24)
        main_panel.grid_columnconfigure(0, weight=1)
        main_panel.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(main_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header_text = ctk.CTkFrame(header, fg_color="transparent")
        header_text.pack(side="left")
        ctk.CTkLabel(
            header_text,
            text="AUTOMATION  /  DASHBOARD",
            font=ui_font(9, "bold"),
            text_color=ACCENT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_text,
            text="批量选择任务",
            font=ui_font(25, "bold"),
            text_color=TEXT,
        ).pack(anchor="w", pady=(2, 0))
        self.status_label = ctk.CTkLabel(
            header,
            text="  ●  就绪  ",
            corner_radius=14,
            fg_color=("#E9EEF6", "#182334"),
            text_color=MUTED,
            font=ui_font(11, "bold"),
            height=30,
        )
        self.status_label.pack(side="right")

        setup = ctk.CTkFrame(main_panel, corner_radius=18, fg_color=CARD_BG, border_width=1, border_color=BORDER)
        setup.grid(row=1, column=0, sticky="ew")
        setup.grid_columnconfigure(0, weight=1)
        self._section_title(setup, "目标窗口", "选择已经打开背包页面的游戏窗口", 0)
        window_row = ctk.CTkFrame(setup, fg_color="transparent")
        window_row.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        window_row.grid_columnconfigure(0, weight=1)
        self.window_combo = ctk.CTkComboBox(
            window_row,
            state="readonly",
            height=42,
            corner_radius=10,
            border_color=BORDER,
            fg_color=SURFACE_BG,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            font=ui_font(12),
            dropdown_font=ui_font(12),
        )
        self.window_combo.grid(row=0, column=0, sticky="ew")
        self.refresh_button = ctk.CTkButton(window_row, text="↻  刷新窗口", width=118, height=42, corner_radius=10, font=ui_font(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.refresh_windows)
        self.refresh_button.grid(row=0, column=1, padx=(10, 0))

        sprite_card = ctk.CTkFrame(main_panel, corner_radius=18, fg_color=CARD_BG, border_width=1, border_color=BORDER)
        sprite_card.grid(row=2, column=0, sticky="ew", pady=14)
        sprite_card.configure(height=240)
        sprite_card.grid_propagate(False)
        sprite_card.grid_columnconfigure(0, weight=1)
        sprite_card.grid_rowconfigure(1, weight=1)
        title_row = ctk.CTkFrame(sprite_card, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 10))
        title_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(title_row, text="选择精灵", font=ui_font(17, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        self.selected_count_label = ctk.CTkLabel(title_row, text="已选 0", height=26, corner_radius=13, fg_color=("#EEECFF", "#282450"), text_color=ACCENT, font=ui_font(10, "bold"))
        self.selected_count_label.grid(row=0, column=1, padx=(8, 10))
        self.add_button = ctk.CTkButton(title_row, text="＋  添加模板", width=116, height=36, corner_radius=10, font=ui_font(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.add_sprite)
        self.add_button.grid(row=0, column=2)
        ctk.CTkLabel(
            title_row,
            text="可同时选择多个目标，重复识别只点击一次",
            font=ui_font(11),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.sprite_list = ctk.CTkScrollableFrame(sprite_card, fg_color="transparent")
        self.sprite_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.sprite_list.grid_columnconfigure(0, weight=1)

        console_card = ctk.CTkFrame(main_panel, corner_radius=18, fg_color=CARD_BG, border_width=1, border_color=BORDER)
        console_card.grid(row=3, column=0, sticky="nsew")
        console_card.grid_columnconfigure(0, weight=1)
        console_card.grid_rowconfigure(1, weight=1)
        self._section_title(console_card, "运行日志", "识别进度和诊断信息会显示在这里", 0)
        self.log_text = ctk.CTkTextbox(console_card, height=90, corner_radius=12, border_width=1, border_color=BORDER, fg_color=LOG_BG, text_color=TEXT, wrap="word", font=ctk.CTkFont(family="Cascadia Mono", size=11))
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.log_text.configure(state="disabled")
        self.progress = ctk.CTkProgressBar(console_card, height=3, progress_color=ACCENT)
        self.progress.grid(row=2, column=0, sticky="ew", padx=18)
        self.progress.set(0)

        actions = ctk.CTkFrame(console_card, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=16)
        self.detect_button = ctk.CTkButton(
            actions,
            text="仅检测",
            width=110,
            height=42,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER,
            font=ui_font(12, "bold"),
            command=lambda: self.start(True),
        )
        self.detect_button.pack(side="left")
        self.start_button = ctk.CTkButton(actions, text="▶  开始自动选择", width=164, height=42, corner_radius=10, font=ui_font(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=lambda: self.start(False))
        self.start_button.pack(side="right")
        self.stop_button = ctk.CTkButton(
            actions,
            text="■  停止",
            width=100,
            height=42,
            state="disabled",
            font=ui_font(12, "bold"),
            fg_color=("#AAB2C0", "#334155"),
            hover_color=("#929BAA", "#42526A"),
            command=self.stop,
        )
        self.stop_button.pack(side="right", padx=(0, 10))

    def _step(self, parent: ctk.CTkFrame, number: str, title: str, subtitle: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(row, text=number, width=36, height=36, corner_radius=12, fg_color=("#263449", "#192536"), text_color="#B9C5D8", font=ui_font(10, "bold")).pack(side="left")
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", padx=(11, 0))
        ctk.CTkLabel(text, text=title, font=ui_font(12, "bold"), text_color="#F1F5F9").pack(anchor="w")
        ctk.CTkLabel(text, text=subtitle, font=ui_font(10), text_color="#8290A6").pack(anchor="w", pady=(1, 0))

    def _section_title(self, parent: ctk.CTkFrame, title: str, subtitle: str, row: int) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=0, sticky="ew", padx=20, pady=(16, 10))
        ctk.CTkLabel(box, text=title, font=ui_font(17, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(box, text=subtitle, font=ui_font(11), text_color=MUTED).pack(anchor="w", pady=(2, 0))

    def refresh_windows(self) -> None:
        previous = self.window_combo.get()
        own_title = self.root.title()
        windows = [(hwnd, title) for hwnd, title in visible_windows() if title != own_title]
        self.window_values = {f"{title}  ·  0x{hwnd:X}": hwnd for hwnd, title in windows}
        values = list(self.window_values)
        self.window_combo.configure(values=values or ["没有找到可用窗口"])
        if previous in self.window_values:
            self.window_combo.set(previous)
        elif values:
            self.window_combo.set(values[0])
        else:
            self.window_combo.set("没有找到可用窗口")

    def refresh_sprites(self) -> None:
        for child in self.sprite_list.winfo_children():
            child.destroy()
        self.enabled_vars.clear()
        self.sprite_images.clear()
        for row_index, sprite in enumerate(main.get_sprite_definitions(self.config)):
            row = ctk.CTkFrame(self.sprite_list, corner_radius=12, fg_color=SURFACE_BG, border_width=1, border_color=BORDER)
            row.grid(row=row_index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(2, weight=1)
            variable = tk.BooleanVar(value=sprite.id in self.enabled_ids)
            self.enabled_vars[sprite.id] = variable
            checkbox = ctk.CTkCheckBox(
                row,
                text="",
                width=28,
                corner_radius=6,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=("#ADB7C8", "#526078"),
                variable=variable,
                command=lambda item_id=sprite.id: self.toggle_sprite(item_id),
            )
            checkbox.grid(row=0, column=0, rowspan=2, padx=(14, 5), pady=12)
            thumbnail_box = ctk.CTkFrame(row, width=52, height=52, corner_radius=12, fg_color=("#E7E5FF", "#2B2855"))
            thumbnail_box.grid(row=0, column=1, rowspan=2, padx=(4, 11), pady=8)
            thumbnail_box.grid_propagate(False)
            try:
                with Image.open(main.ASSETS / sprite.unselected) as source:
                    thumbnail = source.convert("RGB")
                    thumbnail.thumbnail((46, 46), Image.Resampling.LANCZOS)
                display = ctk.CTkImage(
                    light_image=thumbnail,
                    dark_image=thumbnail,
                    size=thumbnail.size,
                )
                self.sprite_images[sprite.id] = display
                ctk.CTkLabel(thumbnail_box, text="", image=display).place(relx=0.5, rely=0.5, anchor="center")
            except Exception:
                ctk.CTkLabel(
                    thumbnail_box,
                    text=sprite.name[:1].upper(),
                    text_color=ACCENT,
                    font=ui_font(15, "bold"),
                ).place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(row, text=sprite.name, font=ui_font(13, "bold"), text_color=TEXT).grid(row=0, column=2, sticky="sw", pady=(9, 0))
            ctk.CTkLabel(row, text=f"TEMPLATE  ·  {sprite.id}", font=ui_font(9, "bold"), text_color=MUTED).grid(row=1, column=2, sticky="nw", pady=(0, 9))
            remove = ctk.CTkButton(
                row,
                text="×",
                width=34,
                height=34,
                corner_radius=10,
                font=ui_font(18),
                fg_color="transparent",
                border_width=1,
                border_color=BORDER,
                text_color=MUTED,
                command=lambda item_id=sprite.id: self.remove_sprite(item_id),
            )
            remove.grid(row=0, column=3, rowspan=2, padx=12)
            if self.running:
                checkbox.configure(state="disabled")
                remove.configure(state="disabled")
        self.update_selected_count()

    def toggle_sprite(self, sprite_id: str) -> None:
        if self.enabled_vars[sprite_id].get():
            self.enabled_ids.add(sprite_id)
        else:
            self.enabled_ids.discard(sprite_id)
        self.update_selected_count()

    def update_selected_count(self) -> None:
        if hasattr(self, "selected_count_label"):
            self.selected_count_label.configure(text=f"  已选 {len(self.enabled_ids)}  ")

    def save_config(self) -> None:
        temp_path = main.CONFIG_PATH.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(self.config, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temp_path.replace(main.CONFIG_PATH)

    def add_sprite(self) -> None:
        dialog = TemplateDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        name, unselected, selected = dialog.result
        sprite_id = f"sprite_{uuid.uuid4().hex[:8]}"
        target_dir = main.ASSETS / "sprites" / sprite_id
        target_dir.mkdir(parents=True, exist_ok=False)
        unselected_suffix = Path(unselected).suffix.lower() or ".png"
        selected_suffix = Path(selected).suffix.lower() or ".png"
        unselected_target = target_dir / f"unselected{unselected_suffix}"
        selected_target = target_dir / f"selected{selected_suffix}"
        shutil.copy2(unselected, unselected_target)
        shutil.copy2(selected, selected_target)

        sprite = {
            "id": sprite_id,
            "name": name,
            "unselected": unselected_target.relative_to(main.ASSETS).as_posix(),
            "selected": selected_target.relative_to(main.ASSETS).as_posix(),
            "thresholds": {
                "unselected": float(self.config.get("thresholds", {}).get("unselected", 0.86)),
                "selected": float(self.config.get("thresholds", {}).get("selected", 0.80)),
            },
        }
        self.config.setdefault("sprites", []).append(sprite)
        self.enabled_ids.add(sprite_id)
        self.save_config()
        self.refresh_sprites()

    def remove_sprite(self, sprite_id: str) -> None:
        definitions = main.get_sprite_definitions(self.config)
        if len(definitions) <= 1:
            messagebox.showwarning("无法移除", "至少需要保留一种精灵。", parent=self.root)
            return
        sprite = next(item for item in definitions if item.id == sprite_id)
        if not messagebox.askyesno(
            "移除模板",
            f"确定从列表中移除“{sprite.name}”吗？\n模板图片会保留在 assets 目录中。",
            parent=self.root,
        ):
            return
        self.config["sprites"] = [item for item in self.config["sprites"] if item.get("id") != sprite_id]
        self.enabled_ids.discard(sprite_id)
        valid_ids = [item.id for item in main.get_sprite_definitions(self.config)]
        defaults = [item for item in self.config.get("default_sprites", []) if item in valid_ids]
        self.config["default_sprites"] = defaults or [valid_ids[0]]
        self.save_config()
        self.refresh_sprites()

    def start(self, dry_run: bool) -> None:
        if self.running:
            return
        hwnd = self.window_values.get(self.window_combo.get())
        if hwnd is None:
            messagebox.showwarning("请选择窗口", "请先选择要操作的游戏窗口。", parent=self.root)
            return
        sprite_ids = [sprite.id for sprite in main.get_sprite_definitions(self.config) if sprite.id in self.enabled_ids]
        if not sprite_ids:
            messagebox.showwarning("请选择精灵", "请至少选择一种精灵。", parent=self.root)
            return

        self.running = True
        self.stop_event.clear()
        self.set_running_controls(True)
        self.set_status("检测中" if dry_run else "运行中", active=True)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.append_log("\n" + "─" * 54 + "\n")
        threading.Thread(target=self.run_worker, args=(dry_run, sprite_ids, hwnd), daemon=True).start()

    def run_worker(self, dry_run: bool, sprite_ids: list[str], hwnd: int) -> None:
        writer = QueueWriter(self.output_queue)
        exit_code = 1
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                exit_code = main.run(
                    dry_run=dry_run,
                    sprite_ids=sprite_ids,
                    target_hwnd=hwnd,
                    stop_event=self.stop_event,
                    debug_callback=self.queue_debug_preview,
                )
        except KeyboardInterrupt:
            writer.write("\n已停止。\n")
            exit_code = 130
        except Exception as error:
            writer.write(f"\n运行失败：{error}\n")
        self.output_queue.put(("done", exit_code))

    def queue_debug_preview(self, image: np.ndarray, label: str) -> None:
        self.output_queue.put(("preview", (image.copy(), label)))

    def show_debug_preview(self, image: np.ndarray, label: str) -> None:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        source = Image.fromarray(rgb)
        max_width = min(920, self.root.winfo_screenwidth() - 160)
        max_height = min(600, self.root.winfo_screenheight() - 220)
        scale = min(max_width / source.width, max_height / source.height, 1.0)
        size = (max(1, int(source.width * scale)), max(1, int(source.height * scale)))

        preview = ctk.CTkToplevel(self.root)
        preview.title(label)
        preview.configure(fg_color=APP_BG)
        preview.geometry(f"{max(620, size[0] + 48)}x{size[1] + 132}")
        preview.transient(self.root)

        header = ctk.CTkFrame(preview, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 12))
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(title_box, text=label, font=ui_font(18, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="图片仅保存在内存中，关闭此窗口后即释放。",
            font=ui_font(10),
            text_color=SUCCESS,
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(
            header,
            text="关闭",
            width=82,
            height=34,
            corner_radius=10,
            font=ui_font(11, "bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=preview.destroy,
        ).pack(side="right")

        display_image = ctk.CTkImage(light_image=source, dark_image=source, size=size)
        image_card = ctk.CTkFrame(preview, corner_radius=14, fg_color=CARD_BG, border_width=1, border_color=BORDER)
        image_card.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        image_label = ctk.CTkLabel(image_card, text="", image=display_image)
        image_label.pack(expand=True, padx=8, pady=8)
        preview._display_image = display_image
        preview.after(100, preview.focus_force)

    def stop(self) -> None:
        if self.running:
            self.stop_event.set()
            self.set_status("正在停止", active=True)

    def set_status(self, text: str, active: bool = False) -> None:
        self.status_label.configure(
            text=f"  ●  {text}  ",
            fg_color=("#E7E5FF", "#282450") if active else ("#E9EEF6", "#182334"),
            text_color=ACCENT if active else MUTED,
        )

    def set_running_controls(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.start_button.configure(state=state)
        self.detect_button.configure(state=state)
        self.refresh_button.configure(state=state)
        self.add_button.configure(state=state)
        self.window_combo.configure(state="disabled" if running else "readonly")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.refresh_sprites()

    def append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def poll_output(self) -> None:
        try:
            while True:
                kind, value = self.output_queue.get_nowait()
                if kind == "log":
                    self.append_log(value)
                elif kind == "preview":
                    image, label = value
                    self.show_debug_preview(image, label)
                elif kind == "done":
                    self.running = False
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress.set(1 if value == 0 else 0)
                    self.set_running_controls(False)
                    if value == 0:
                        self.set_status("已完成")
                    elif value == 130:
                        self.set_status("已停止")
                    else:
                        self.set_status(f"已结束 · {value}")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_output)

    def on_close(self) -> None:
        if self.running and not messagebox.askyesno("退出", "任务仍在运行，确定停止并退出吗？", parent=self.root):
            return
        self.stop_event.set()
        self.root.destroy()


def main_gui() -> None:
    main.enable_dpi_awareness()
    root = ctk.CTk()
    SpriteApp(root)
    root.mainloop()


def smoke_test() -> int:
    config = main.load_config()
    main.load_image("next_page.png")
    main.load_image("pagination.png")
    main.load_sprite_templates(config)
    main.MouseClicker(mode="send_input")
    main.MouseClicker(mode="interception", fallback_on_missing=True)
    return 0


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    main_gui()
