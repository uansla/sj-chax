import csv
import io
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import unicodedata
import re

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

    FIELD_ALIASES = {
        "series": ["系列", "品牌/系列", "系列分类", "分类"],
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
        self.all_data = []
        self.load_errors = []

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

    def setup_ui(self):
        top = ttk.Frame(self.root, padding=15)
        top.pack(fill=tk.X)
        ttk.Label(top, text="🔍 搜索型号/品牌:", font=self.font_header).pack(side=tk.LEFT)

        search_frame = tk.Frame(top)
        search_frame.pack(side=tk.LEFT, padx=15)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.do_search())
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var, font=self.font_search, width=40, relief="solid", borderwidth=1)
        self.search_entry.pack(side=tk.LEFT, ipady=4)
        tk.Button(search_frame, text="✕", command=self.clear_search, font=("微软雅黑", 12, "bold"), relief="flat", bd=0, cursor="hand2", padx=7).pack(side=tk.LEFT)

        tk.Button(top, text="🔄 刷新数据", command=self.load_all_data, font=self.font_main, bg="#f0f0f0", padx=10).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="🗑 清空", command=self.clear_search, font=self.font_main, bg="#f0f0f0", padx=10).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="📂 打开数据夹", command=self.open_data_folder, font=self.font_main, bg="#f0f0f0", padx=10).pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(top, text="", font=self.font_main, foreground="#666666")
        self.status_label.pack(side=tk.RIGHT)

        self.columns = [
            ("source", "品牌", 110),
            ("series", "系列", 150),
            ("no", "序号", 65),
            ("model", "机型规格", 320),
            ("network", "网络型号", 160),
            ("p1", "靓好", 95),
            ("p2", "好屏", 95),
            ("p3", "碎屏", 95),
            ("p4", "坏配件", 95),
            ("p5", "不开机", 95),
            ("p6", "废板", 95),
            ("bulk", "统货", 95),
            ("remark", "备注说明", 420),
        ]

        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.tree = ttk.Treeview(frame, columns=[x[0] for x in self.columns], show="headings", style="Custom.Treeview")
        for col_id, col_name, width in self.columns:
            self.tree.heading(col_id, text=col_name)
            anchor = tk.CENTER if col_id in {"no", "network", "p1", "p2", "p3", "p4", "p5", "p6", "bulk"} else tk.W
            self.tree.column(col_id, width=width, minwidth=45, anchor=anchor)
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

    @staticmethod
    def clean_text(value):
        if value is None:
            return ""
        value = unicodedata.normalize("NFKC", str(value))
        value = value.replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
        return re.sub(r"\s+", " ", value).strip()

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

        return {
            "source": brand,
            "series": self.get_field(clean_row, self.FIELD_ALIASES["series"], brand),
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
        }

    def load_all_data(self):
        query = self.search_var.get()
        self.all_data.clear()
        self.load_errors.clear()

        try:
            csv_files = sorted(
                os.path.join(self.data_dir, name)
                for name in os.listdir(self.data_dir)
                if name.lower().endswith(".csv")
            )
        except OSError as exc:
            csv_files = []
            self.load_errors.append(f"数据目录读取失败: {exc}")

        loaded_files = 0
        for f_path in csv_files:
            brand = os.path.splitext(os.path.basename(f_path))[0]
            try:
                rows, _encoding = self.read_csv_rows(f_path)
                file_count = 0
                for row in rows:
                    item = self.normalize_row(row, brand)
                    if item:
                        self.all_data.append(item)
                        file_count += 1

                if file_count:
                    loaded_files += 1
                else:
                    self.load_errors.append(f"{os.path.basename(f_path)}: 未找到有效机型数据")
            except Exception as exc:
                self.load_errors.append(f"{os.path.basename(f_path)}: {type(exc).__name__}: {exc}")
                print("⚠️", self.load_errors[-1])

        status = f"已加载 {loaded_files} 个数据文件，共 {len(self.all_data)} 行数据"
        if self.load_errors:
            status += f" · {len(self.load_errors)} 个文件异常"
        self.status_label.config(text=status)

        self.search_var.set(query)
        self.do_search()

        for err in self.load_errors:
            print("⚠️", err)

    @classmethod
    def search_tokens(cls, value):
        cleaned = cls.clean_text(value).casefold()
        return [x for x in re.split(r"[\s,，/\\_\-—–·•（）()【】\[\].:：]+", cleaned) if x]

    def do_search(self):
        raw_query = self.search_var.get()
        query = self.search_key(raw_query)
        tokens = self.search_tokens(raw_query)

        for item in self.tree.get_children():
            self.tree.delete(item)

        count = 0
        for d in self.all_data:
            searchable = self.search_key(" ".join(str(d.get(k, "")) for k, _, _ in self.columns))
            if not query or all(self.search_key(token) in searchable for token in tokens):
                tag = "oddrow" if count % 2 == 0 else "evenrow"
                self.tree.insert("", tk.END, values=tuple(d.get(k, "") for k, _, _ in self.columns), tags=(tag,))
                count += 1

        base = self.status_label.cget("text").split(" | 当前搜索", 1)[0]
        self.status_label.config(text=base + (f" | 当前搜索 {count} 行" if raw_query.strip() else ""))


if __name__ == "__main__":
    root = tk.Tk()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    app = PhonePriceSearchApp(root)
    root.mainloop()
