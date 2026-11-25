import csv
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import unicodedata
import re
import threading
import ipaddress
import tkinter.font as tkfont
from datetime import datetime, timedelta

from series_classifier import infer_series

# 开启 Windows 高分屏缩放优化 (防止模糊)
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class PhonePriceSearchApp:
    """本地 CSV 查价工具。

    兼容：
    1. UTF-8 / UTF-8 BOM / GB18030 / GBK
    2. 不同品牌历史数据使用的字段名差异
    3. 一个 CSV 内存在多张表、多个表头
    4. .csv / .CSV 扩展名
    5. 中文、英文、数字混合型号搜索
    6. “oppo A5”这类多词搜索采用 AND 匹配
    """

    CATEGORY_OPTIONS = ("二手手机", "手机内配", "杂货铺", "数码相机回收报价", "电脑回收", "二手平板", "家电回收")

    FIELD_ALIASES = {
        "category": ["分类", "品类", "商品分类"],
        "series": ["系列", "品牌/系列", "系列分类"],
        "model": ["型号", "机型及配置", "机型与配置", "机型及规格", "机型与规格", "机型规格", "机型", "品名/型号"],
        "p1": ["开机靓好", "开机靓机好", "靓好", "开机屏好", "开机屏好(无ID)", "开机屏好(元)"],
        "p2": ["开机好屏", "开机好碎", "开机屏好碎壳", "开机屏好外屏碎", "开机外屏碎", "好屏", "好碎"],
        "p3": ["开机碎屏", "开机屏坏/外碎", "开机屏坏未标", "开机屏坏", "碎屏"],
        "p4": ["开机压屏", "开机压屏机", "开机坏配件", "压屏", "坏配件"],
        "p5": ["不开机", "不开机(元)", "不开机屏好"],
        "p6": ["废板-整机", "废板·整机", "废板·断板", "废板-整机(元)", "废板·断板", "废板整机", "废板", "深板·整机", "深板·整机/国产", "国产屏/整机"],
        "bulk": ["统货", "开机无灯光", "无灯光"],
        "network": ["网络型号", "网络制式型号", "网络制式", "网络型号/制式"],
        "remark": ["备注", "备注说明"],
    }

    def __init__(self, root):
        self.root = root
        self.root.title("数码回收价格秒查工具 - 专业大字版")
        self.root.geometry("1750x900")
        self.root.minsize(1100, 650)

        self.base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.settings_path = os.path.join(self.base_dir, "app_settings.json")
        self.cache_path = os.path.join(self.base_dir, "price_cache.json")
        self.network_enabled, self.proxy_enabled, self.proxy_ip, self.proxy_port = self.load_preferences()
        self.all_data = []
        self.load_errors = []
        self.syncing = False
        self.extra_columns = []
        self.base_columns = None
        self.date_user_selected = False
        self.selected_category = "二手手机"
        self.selected_brand = "oppo"
        self.selected_series = "全部"
        self.category_tag_width = 0
        self.brand_tag_width = 0
        self.series_tag_width = 0

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.font_main = ("微软雅黑", 12)
        self.font_header = ("微软雅黑", 13, "bold")
        self.font_search = ("微软雅黑", 14)
        self.style.configure("Custom.Treeview", font=self.font_main, rowheight=35, background="white", foreground="black", fieldbackground="white")
        self.style.configure("Custom.Treeview.Heading", font=self.font_header, background="#eeeeee")
        self.style.map("Custom.Treeview", background=[("selected", "#0078d7")], foreground=[("selected", "white")])
        self.setup_ui()
        self.load_all_data()
        if self.network_enabled:
            self.status_label.config(text="联网更新已开启；点击更新按钮选择分类和日期")

    def load_preferences(self):
        defaults = {
            "network_enabled": False,
            "proxy_enabled": False,
            "proxy_ip": "",
            "proxy_port": "",
        }
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                defaults.update(saved)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
        return (
            bool(defaults.get("network_enabled", False)),
            bool(defaults.get("proxy_enabled", False)),
            str(defaults.get("proxy_ip", "") or ""),
            str(defaults.get("proxy_port", "") or ""),
        )

    def save_network_preference(self):
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump({
                    "network_enabled": self.network_enabled,
                    "proxy_enabled": self.proxy_enabled,
                    "proxy_ip": self.proxy_ip,
                    "proxy_port": self.proxy_port,
                }, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showwarning("设置未保存", f"无法保存设置：\n{exc}")

    def open_proxy_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("官网更新代理设置")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        enabled_var = tk.BooleanVar(value=self.proxy_enabled)
        ip_var = tk.StringVar(value=self.proxy_ip)
        port_var = tk.StringVar(value=self.proxy_port)

        body = ttk.Frame(dialog, padding=16)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Checkbutton(body, text="使用 HTTP 代理", variable=enabled_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(body, text="代理 IP：").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=4)
        ip_entry = ttk.Entry(body, textvariable=ip_var, width=25)
        ip_entry.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="端口：").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=4)
        ttk.Entry(body, textvariable=port_var, width=25).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="默认不使用代理，直接通过本机网络连接。").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 12)
        )

        def save():
            ip_value = ip_var.get().strip()
            port_value = port_var.get().strip()
            if enabled_var.get():
                try:
                    ipaddress.ip_address(ip_value)
                    port_number = int(port_value)
                    if not 1 <= port_number <= 65535:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("代理设置无效", "请输入有效的代理 IP 和 1–65535 范围内的端口。", parent=dialog)
                    return
            self.proxy_enabled = bool(enabled_var.get())
            self.proxy_ip = ip_value
            self.proxy_port = port_value
            self.save_network_preference()
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(buttons, text="保存", command=save).pack(side=tk.RIGHT)
        ip_entry.focus_set()

    def on_date_selected(self, *_):
        self.date_user_selected = True
        self.do_search()

    def on_category_tag_resize(self, event):
        if event.width != self.category_tag_width:
            self.category_tag_width = event.width
            self.root.after_idle(self.render_category_tags)

    def render_category_tags(self):
        if not hasattr(self, "category_tags_frame"):
            return
        for child in self.category_tags_frame.winfo_children():
            child.destroy()
        for name in self.CATEGORY_OPTIONS:
            color = "#c0392b" if name == self.selected_category else "#333333"
            tag = tk.Label(self.category_tags_frame, text=name, font=self.font_main, fg=color,
                           bg="white", cursor="hand2", padx=8, pady=3)
            tag.pack(side=tk.LEFT)
            tag.bind("<Button-1>", lambda _event, selected=name: self.select_category(selected))

    def on_brand_tag_resize(self, event):
        if event.width != self.brand_tag_width:
            self.brand_tag_width = event.width
            self.root.after_idle(self.render_brand_tags)

    def render_brand_tags(self):
        if not hasattr(self, "brand_tags_frame"):
            return
        for child in self.brand_tags_frame.winfo_children():
            child.destroy()
        brands = sorted({
            str(row.get("source", "")).strip() for row in self.all_data
            if row.get("source") and row.get("category", "二手手机") == self.selected_category
        }, key=str.casefold)
        options = ["全部"] + brands
        available_width = max(self.brand_tags_frame.winfo_width(), self.root.winfo_width() - 100, 400)
        tag_font = tkfont.Font(root=self.root, font=self.font_main)
        rows = [[]]
        used_width = 0
        for name in options:
            needed = tag_font.measure(name) + 22
            if rows[-1] and used_width + needed > available_width:
                rows.append([])
                used_width = 0
            rows[-1].append(name)
            used_width += needed
        for row in rows:
            row_frame = tk.Frame(self.brand_tags_frame, bg="white")
            row_frame.pack(anchor=tk.W, fill=tk.X)
            for name in row:
                color = "#c0392b" if name == self.selected_brand else "#333333"
                tag = tk.Label(row_frame, text=name, font=self.font_main, fg=color, bg="white",
                               cursor="hand2", padx=8, pady=3)
                tag.pack(side=tk.LEFT)
                tag.bind("<Button-1>", lambda _event, selected=name: self.select_brand(selected))
    def on_series_tag_resize(self, event):
        if event.width != self.series_tag_width:
            self.series_tag_width = event.width
            self.root.after_idle(self.render_series_tags)

    def render_series_tags(self):
        if not hasattr(self, "series_tags_frame"):
            return
        for child in self.series_tags_frame.winfo_children():
            child.destroy()
        rows = [
            row for row in self.all_data
            if row.get("category", "二手手机") == self.selected_category
            and (self.selected_brand == "全部" or row.get("source") == self.selected_brand)
        ]
        series = sorted({str(row.get("series", "")).strip() for row in rows if row.get("series")}, key=str.casefold)
        options = ["全部"] + series
        if self.selected_series not in options:
            self.selected_series = "全部"
        available_width = max(self.series_tags_frame.winfo_width(), self.root.winfo_width() - 100, 400)
        tag_font = tkfont.Font(root=self.root, font=self.font_main)
        tag_rows = [[]]
        used_width = 0
        for name in options:
            needed = tag_font.measure(name) + 22
            if tag_rows[-1] and used_width + needed > available_width:
                tag_rows.append([])
                used_width = 0
            tag_rows[-1].append(name)
            used_width += needed
        for row in tag_rows:
            row_frame = tk.Frame(self.series_tags_frame, bg="white")
            row_frame.pack(anchor=tk.W, fill=tk.X)
            for name in row:
                color = "#c0392b" if name == self.selected_series else "#333333"
                tag = tk.Label(row_frame, text=name, font=self.font_main, fg=color, bg="white",
                               cursor="hand2", padx=8, pady=3)
                tag.pack(side=tk.LEFT)
                tag.bind("<Button-1>", lambda _event, selected=name: self.select_series(selected))

    def select_series(self, series):
        self.selected_series = series
        self.render_series_tags()
        self.do_search()

    def select_category(self, category):
        if category not in self.CATEGORY_OPTIONS:
            return
        self.selected_category = category
        self.selected_brand = "oppo" if category == "二手手机" else "全部"
        self.selected_series = "全部"
        self.date_user_selected = False
        available_dates = sorted({
            row.get("date", "") for row in self.all_data
            if row.get("date") and row.get("category", "二手手机") == category
        }, reverse=True)
        date_values = ["全部日期"] + available_dates
        self.date_combo.configure(values=date_values)
        self.date_var.set(available_dates[0] if available_dates else "全部日期")
        self.render_category_tags()
        self.render_brand_tags()
        self.render_series_tags()
        self.do_search()

    def select_brand(self, brand):
        self.selected_brand = brand
        self.selected_series = "全部"
        self.render_brand_tags()
        self.render_series_tags()
        self.do_search()

    def on_network_toggle(self):
        self.network_enabled = bool(self.network_var.get())
        self.save_network_preference()
        if self.network_enabled:
            self.status_label.config(text="联网已开启，请选择更新分类和日期")
            self.sync_online()
        else:
            self.sync_button.config(state=tk.DISABLED)
            self.status_label.config(text="离线模式：仅使用本地 data 文件夹中的报价")

    def setup_ui(self):
        top = ttk.Frame(self.root, padding=15)
        top.pack(fill=tk.X)
        ttk.Label(top, text="🔍 搜索型号/品牌:", font=self.font_header).pack(side=tk.LEFT)

        ttk.Label(top, text="报价日期:", font=self.font_header).pack(side=tk.LEFT, padx=(14, 4))
        self.date_var = tk.StringVar(value="全部日期")
        self.date_combo = ttk.Combobox(top, textvariable=self.date_var, state="readonly", width=13, values=["全部日期"])
        self.date_combo.pack(side=tk.LEFT, padx=(0, 12))
        self.date_combo.bind("<<ComboboxSelected>>", self.on_date_selected)

        self.network_var = tk.BooleanVar(value=self.network_enabled)
        self.network_toggle = ttk.Checkbutton(
            top,
            text="联网更新",
            variable=self.network_var,
            command=self.on_network_toggle,
        )
        self.network_toggle.pack(side=tk.LEFT, padx=(0, 8))

        search_frame = tk.Frame(top)
        search_frame.pack(side=tk.LEFT, padx=15)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.do_search())
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var, font=self.font_search, width=40, relief="solid", borderwidth=1)
        self.search_entry.pack(side=tk.LEFT, ipady=4)
        tk.Button(search_frame, text="✕", command=self.clear_search, font=("微软雅黑", 12, "bold"), relief="flat", bd=0, cursor="hand2", padx=7).pack(side=tk.LEFT)

        self.sync_button = tk.Button(top, text="🌐 更新官网报价", command=self.sync_online, font=self.font_main, bg="#e8f3ff", padx=10)
        self.sync_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="⚙ 代理设置", command=self.open_proxy_settings).pack(side=tk.LEFT, padx=5)
        if not self.network_enabled:
            self.sync_button.config(state=tk.DISABLED)
        tk.Button(top, text="🔄 重新加载", command=self.load_all_data, font=self.font_main, bg="#f0f0f0", padx=10).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="📂 打开数据夹", command=self.open_data_folder, font=self.font_main, bg="#f0f0f0", padx=10).pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(top, text="", font=self.font_main, foreground="#666666")
        self.status_label.pack(side=tk.RIGHT)

        self.columns = [
            ("date", "报价日期", 110),
            ("source", "品牌", 110),
            ("series", "系列", 150),
            ("no", "序号", 65),
            ("model", "机型规格", 320),
            ("network", "网络型号", 160),
            ("remark", "备注说明", 300),
        ]
        self.base_columns = list(self.columns)

        self.category_tag_container = ttk.Frame(self.root, padding=(15, 2))
        self.category_tag_container.pack(fill=tk.X)
        ttk.Label(self.category_tag_container, text="分类:", font=self.font_main).pack(side=tk.LEFT, anchor=tk.NW, padx=(0, 8))
        self.category_tags_frame = tk.Frame(self.category_tag_container, bg="white")
        self.category_tags_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.category_tag_container.bind("<Configure>", self.on_category_tag_resize)

        self.brand_tag_container = ttk.Frame(self.root, padding=(15, 4))
        self.brand_tag_container.pack(fill=tk.X)
        ttk.Label(self.brand_tag_container, text="品牌:", font=self.font_main).pack(side=tk.LEFT, anchor=tk.NW, padx=(0, 8))
        self.brand_tags_frame = tk.Frame(self.brand_tag_container, bg="white")
        self.brand_tags_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.brand_tag_container.bind("<Configure>", self.on_brand_tag_resize)

        self.series_tag_container = ttk.Frame(self.root, padding=(15, 2))
        self.series_tag_container.pack(fill=tk.X)
        ttk.Label(self.series_tag_container, text="系列:", font=self.font_main).pack(side=tk.LEFT, anchor=tk.NW, padx=(0, 8))
        self.series_tags_frame = tk.Frame(self.series_tag_container, bg="white")
        self.series_tags_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.series_tag_container.bind("<Configure>", self.on_series_tag_resize)

        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.tree = ttk.Treeview(frame, columns=[x[0] for x in self.columns], show="headings", style="Custom.Treeview")
        for col_id, col_name, width in self.columns:
            self.tree.heading(col_id, text=col_name)
            anchor = tk.CENTER if col_id in {"no", "network", "p1", "p2", "p3", "p4", "p5", "p6", "bulk"} else tk.W
            self.tree.column(col_id, width=width, minwidth=45, anchor=anchor, stretch=False)
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        self.tree.tag_configure("oddrow", background="#f9f9f9")
        self.tree.tag_configure("evenrow", background="#ffffff")
        self.search_entry.bind("<Return>", lambda *_: self.do_search())
        self.search_entry.focus_set()

    def clear_search(self):
        self.search_var.set("")
        self.search_entry.focus_set()

    def open_data_folder(self):
        try:
            if sys.platform == "win32":
                os.startfile(self.data_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.data_dir])
            else:
                subprocess.Popen(["xdg-open", self.data_dir])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹:\n{e}")

    def sync_online(self):
        if not self.network_enabled:
            return
        if self.syncing:
            return
        self.syncing = True
        self.sync_button.config(state=tk.DISABLED)
        self.network_toggle.config(state=tk.DISABLED)
        self.status_label.config(text="正在连接报价网站并更新…")

        def worker():
            try:
                from auto_pipeline import run_pipeline
                proxies = None
                if self.proxy_enabled:
                    address = ipaddress.ip_address(self.proxy_ip)
                    host = f"[{address}]" if address.version == 6 else str(address)
                    proxy_url = f"http://{host}:{self.proxy_port}"
                    proxies = {"http": proxy_url, "https": proxy_url}
                result = run_pipeline(
                    lambda message: self.root.after(0, lambda m=message: self.status_label.config(text=m)),
                    data_dir=self.data_dir,
                    proxies=proxies,
                )
                error = None
            except Exception as exc:
                result, error = None, f"{type(exc).__name__}: {exc}"

            def finish():
                self.syncing = False
                self.sync_button.config(state=tk.NORMAL)
                self.network_toggle.config(state=tk.NORMAL)
                self.load_all_data()
                if error:
                    base = self.status_label.cget("text").split(" | 当前搜索", 1)[0]
                    self.status_label.config(text=base + " · 联网更新失败（保留本地数据）")
                    messagebox.showwarning("联网更新失败", f"无法更新报价：\n{error}\n\n已保留本地已有数据。请检查网络后点击“更新官网报价”。")
                else:
                    self.status_label.config(text=f"更新完成：{result['snapshots']} 份报价 / {result['rows']} 条机型 · {datetime.now():%H:%M}")
            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def clean_text(value):
        if value is None:
            return ""
        value = unicodedata.normalize("NFKC", str(value))
        value = value.replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def has_display_value(cls, value):
        text = cls.clean_text(value).casefold()
        return text not in {"", "-", "--", "—", "–", "/", "\\", "暂无", "无", "n/a", "na", "null", "none"}

    @classmethod
    def search_key(cls, value):
        value = cls.clean_text(value).casefold()
        return re.sub(r"[\s_\-—–·•/\\（）()【】\[\],，.:：]+", "", value)

    @classmethod
    def get_field(cls, row, aliases, default=""):
        normalized = {cls.search_key(k): cls.clean_text(v) for k, v in row.items() if k is not None}
        for alias in aliases:
            value = normalized.get(cls.search_key(alias), "")
            if value:
                return value
        return default

    @classmethod
    def is_header_row(cls, row):
        normalized = {cls.search_key(x) for x in row if cls.clean_text(x)}
        model_markers = {cls.search_key(x) for x in cls.FIELD_ALIASES["model"]}
        other_markers = set()
        for key in ("series", "p1", "p2", "p3", "p4", "p5", "p6", "bulk", "network", "remark"):
            other_markers.update(cls.search_key(x) for x in cls.FIELD_ALIASES[key])
        return bool(normalized & model_markers) and bool(normalized & (other_markers | {cls.search_key("序号")}))

    @classmethod
    def is_separator_row(cls, row):
        text = "".join(cls.clean_text(x) for x in row)
        return bool(text) and len(text) >= 5 and all(c in "=-_ " for c in text)

    def read_csv_rows(self, path):
        """读取一个 CSV 中的所有表格区块；支持不同编码、说明行和多个表头。"""
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                result = []
                header = None
                with open(path, "r", encoding=encoding, newline="") as f:
                    for raw in csv.reader(f):
                        row = [self.clean_text(x) for x in raw]
                        if not row or not any(row):
                            continue
                        if self.is_separator_row(row):
                            continue

                        if self.is_header_row(row):
                            header = row
                            continue

                        if not header:
                            continue

                        if len(row) < len(header):
                            row += [""] * (len(header) - len(row))
                        elif len(row) > len(header):
                            row = row[:len(header)]

                        result.append(dict(zip(header, row)))

                if header is None:
                    raise ValueError("未找到有效的 CSV 表头")
                return result, encoding
            except (UnicodeDecodeError, UnicodeError, csv.Error, ValueError) as exc:
                last_error = exc
        raise last_error or ValueError("无法读取 CSV 文件")

    def normalize_row(self, row, brand):
        clean_row = {self.clean_text(k): self.clean_text(v) for k, v in row.items() if k is not None}
        model = self.get_field(clean_row, self.FIELD_ALIASES["model"], "")

        if not model or self.search_key(model) in {
            self.search_key("型号"), self.search_key("机型"), self.search_key("机型与配置"),
            self.search_key("机型及配置"), self.search_key("机型与规格"), self.search_key("机型及规格")
        }:
            return None

        series = self.get_field(clean_row, self.FIELD_ALIASES["series"], brand)
        if not series or self.search_key(series) == self.search_key(brand):
            series = infer_series(brand, model)

        return {
            "date": self.get_field(clean_row, ["报价日期", "日期", "更新日期"], ""),
            "source": brand,
            "series": series,
            "no": self.get_field(clean_row, ["序号", "编号"], "-"),
            "model": model,
            "network": self.get_field(clean_row, self.FIELD_ALIASES["network"], "/"),
            "p1": self.get_field(clean_row, self.FIELD_ALIASES["p1"], "-"),
            "p2": self.get_field(clean_row, self.FIELD_ALIASES["p2"], "-"),
            "p3": self.get_field(clean_row, self.FIELD_ALIASES["p3"], "-"),
            "p4": self.get_field(clean_row, self.FIELD_ALIASES["p4"], "-"),
            "p5": self.get_field(clean_row, self.FIELD_ALIASES["p5"], "-"),
            "p6": self.get_field(clean_row, self.FIELD_ALIASES["p6"], "-"),
            "bulk": self.get_field(clean_row, self.FIELD_ALIASES["bulk"], "-"),
            "remark": self.get_field(clean_row, self.FIELD_ALIASES["remark"], ""),
            **{key: value for key, value in clean_row.items() if key not in {"报价日期", "日期", "更新日期", "系列", "品牌/系列", "型号", "序号", "网络制式型号", "来源"}},
        }

    def brand_for_csv(self, path):
        parent = os.path.dirname(path)
        if os.path.abspath(parent) != os.path.abspath(self.data_dir):
            return os.path.basename(parent)
        name = os.path.splitext(os.path.basename(path))[0]
        name = re.sub(r"^20\d{2}-\d{2}-\d{2}_", "", name)
        name = re.sub(r"(?:手机)?回收价格(?:表)?$", "", name).strip(" _-")
        return name or "未知品牌"

    def load_all_data(self):
        query = self.search_var.get()
        self.all_data.clear()
        self.load_errors.clear()

        try:
            csv_files = sorted(
                os.path.join(folder, name)
                for folder, _subdirs, names in os.walk(self.data_dir)
                for name in names
                if name.lower().endswith(".csv")
            )
        except OSError as exc:
            csv_files = []
            self.load_errors.append(f"数据目录读取失败: {exc}")

        old_files = {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as cache_file:
                saved_cache = json.load(cache_file)
            if saved_cache.get("version") == 3 and isinstance(saved_cache.get("files"), dict):
                old_files = saved_cache["files"]
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

        new_files = {}
        cache_dirty = set(old_files) != set(csv_files)
        loaded_files = 0
        all_headers = set()
        for f_path in csv_files:
            try:
                stat = os.stat(f_path)
            except OSError as exc:
                self.load_errors.append(f"{os.path.basename(f_path)}: {type(exc).__name__}: {exc}")
                continue

            cached = old_files.get(f_path, {})
            unchanged = (
                cached.get("size") == stat.st_size
                and cached.get("mtime_ns") == stat.st_mtime_ns
                and isinstance(cached.get("rows"), list)
            )
            if unchanged:
                normalized_rows = cached.get("rows", [])
                headers = cached.get("headers", [])
                file_error = cached.get("error")
            else:
                cache_dirty = True
                normalized_rows = []
                headers = []
                file_error = None
                try:
                    raw_rows, _encoding = self.read_csv_rows(f_path)
                    headers = sorted({self.clean_text(key) for row in raw_rows for key in row if key})
                    for row in raw_rows:
                        item = self.normalize_row(row, self.brand_for_csv(f_path))
                        if item:
                            normalized_rows.append(item)
                    if not normalized_rows:
                        file_error = f"{os.path.basename(f_path)}: 未找到有效机型数据"
                except Exception as exc:
                    file_error = f"{os.path.basename(f_path)}: {type(exc).__name__}: {exc}"

            self.all_data.extend(normalized_rows)
            all_headers.update(headers)
            if normalized_rows:
                loaded_files += 1
            if file_error:
                self.load_errors.append(file_error)
                if not unchanged:
                    print("⚠️", file_error)

            new_files[f_path] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "rows": normalized_rows,
                "headers": headers,
                "error": file_error,
            }

        cache_dirty = cache_dirty or set(new_files) != set(old_files)
        if cache_dirty:
            try:
                temp_cache = self.cache_path + ".tmp"
                with open(temp_cache, "w", encoding="utf-8") as cache_file:
                    json.dump({"version": 3, "files": new_files}, cache_file, ensure_ascii=False, separators=(",", ":"))
                os.replace(temp_cache, self.cache_path)
            except (OSError, TypeError, ValueError) as exc:
                print(f"⚠️ 报价缓存无法保存: {exc}")

        available_dates = sorted({row.get("date", "") for row in self.all_data if row.get("date")}, reverse=True)
        old_date = self.date_var.get()
        date_values = ["全部日期"] + available_dates
        self.date_combo.configure(values=date_values)
        if self.date_user_selected and old_date in date_values:
            self.date_var.set(old_date)
        else:
            self.date_var.set(available_dates[0] if available_dates else "全部日期")
        self.render_brand_tags()
        self.render_series_tags()

        reserved = {"报价日期", "日期", "更新日期", "系列", "品牌/系列", "分类", "型号", "机型", "序号", "网络制式型号", "来源", "备注"}
        non_price_aliases = {
            self.clean_text(alias)
            for key, values in self.FIELD_ALIASES.items()
            if key not in {"p1", "p2", "p3", "p4", "p5", "p6", "bulk"}
            for alias in values
        }
        self.extra_columns = sorted(
            (h for h in all_headers if h and h not in reserved and h not in non_price_aliases),
            key=str.casefold,
        )
        self.available_columns_by_scope = {}
        optional_columns = [column[0] for column in self.base_columns if column[0] not in {"date", "source", "series", "model"}]
        candidate_columns = optional_columns + self.extra_columns
        for row in self.all_data:
            row_date = row.get("date") or "全部日期"
            brand = row.get("source") or ""
            series = row.get("series") or ""
            populated = [
                col_id for col_id in candidate_columns
                if self.has_display_value(row.get(col_id, ""))
            ]
            if not populated:
                continue
            scopes = {
                (row_date, brand, series),
                (row_date, brand, "全部"),
                (row_date, "全部", series),
                (row_date, "全部", "全部"),
                ("全部日期", brand, series),
                ("全部日期", brand, "全部"),
                ("全部日期", "全部", series),
                ("全部日期", "全部", "全部"),
            }
            for scope in scopes:
                self.available_columns_by_scope.setdefault(scope, set()).update(populated)
        self.refresh_visible_columns()

        status = f"已加载最近报价 {loaded_files} 份，共 {len(self.all_data)} 条报价"
        if not csv_files:
            status = "本地 data 文件夹中尚无 CSV 报价"
        if self.load_errors:
            status += f" · {len(self.load_errors)} 个文件异常"
        self.status_label.config(text=status)

        self.search_var.set(query)
        self.do_search()

        for err in self.load_errors:
            print("⚠️", err)

    def refresh_visible_columns(self):
        if not hasattr(self, "available_columns_by_scope"):
            return
        scope = (self.date_var.get(), self.selected_brand, self.selected_series)
        populated = self.available_columns_by_scope.get(scope, set())
        required = {"date", "source", "series", "model"}
        visible = [
            column for column in self.base_columns
            if column[0] in required or column[0] in populated
        ]
        visible.extend((header, header, 115) for header in self.extra_columns if header in populated)
        ids = [column[0] for column in visible]
        if ids == [column[0] for column in self.columns]:
            return
        self.columns = visible
        self.tree["columns"] = ids
        for col_id, title, width in self.columns:
            self.tree.heading(col_id, text=title)
            anchor = tk.CENTER if col_id in {"no", "network", "p1", "p2", "p3", "p4", "p5", "p6", "bulk"} else tk.W
            self.tree.column(col_id, width=width, minwidth=45, anchor=anchor, stretch=False)
        self.fit_columns_to_content()

    def fit_columns_to_content(self):
        body_font = tkfont.Font(root=self.root, font=self.font_main)
        heading_font = tkfont.Font(root=self.root, font=self.font_header)
        measured = {}
        for col_id, title, _default_width in self.columns:
            width = heading_font.measure(title) + 22
            for row in self.all_data:
                value = str(row.get(col_id, "") or "")
                if value not in measured:
                    measured[value] = body_font.measure(value)
                width = max(width, measured[value] + 20)
            max_width = 360 if col_id == "remark" else 300
            width = min(max(width, 48), max_width)
            self.tree.column(col_id, width=width, minwidth=45, stretch=False)

    @classmethod
    def search_tokens(cls, value):
        cleaned = cls.clean_text(value).casefold()
        return [x for x in re.split(r"[\s,，/\\_\-—–·•（）()【】\[\].:：]+", cleaned) if x]

    def do_search(self):
        self.refresh_visible_columns()
        raw_query = self.search_var.get()
        query = self.search_key(raw_query)
        tokens = self.search_tokens(raw_query)

        for item in self.tree.get_children():
            self.tree.delete(item)

        count = 0
        selected_date = self.date_var.get()
        for d in self.all_data:
            if self.selected_brand != "全部" and d.get("source") != self.selected_brand:
                continue
            if self.selected_series != "全部" and d.get("series") != self.selected_series:
                continue
            if selected_date != "全部日期" and d.get("date") != selected_date:
                continue
            searchable = self.search_key(" ".join(str(d.get(k, "")) for k, _, _ in self.columns))
            if not query or all(self.search_key(token) in searchable for token in tokens):
                tag = "oddrow" if count % 2 == 0 else "evenrow"
                self.tree.insert("", tk.END, values=tuple(d.get(k, "") for k, _, _ in self.columns), tags=(tag,))
                count += 1

        base = self.status_label.cget("text").split(" | 当前搜索", 1)[0]
        date_text = f" | 日期 {selected_date}" if selected_date != "全部日期" else ""
        search_text = f" | 当前搜索 {count} 行" if raw_query.strip() else ""
        self.status_label.config(text=base + date_text + search_text)


if __name__ == "__main__":
    root = tk.Tk()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    app = PhonePriceSearchApp(root)
    root.mainloop()
