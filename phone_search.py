import csv
import glob
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class PhonePriceSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数码回收价格秒查工具 - 专业大字版")
        self.root.geometry("1750x900")
        self.root.minsize(1100, 650)

        self.base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.all_data = []

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

        # 覆盖 data 中不同 CSV 的全部主要字段；原程序漏掉了网络型号、坏配件、统货等信息
        self.columns = [
            ("source", "品牌", 100), ("series", "系列", 150), ("no", "序号", 65),
            ("model", "机型规格", 300), ("network", "网络型号", 160),
            ("p1", "靓好", 95), ("p2", "好屏", 95), ("p3", "碎屏", 95),
            ("p4", "坏配件", 95), ("p5", "不开机", 95), ("p6", "废板", 95),
            ("bulk", "统货", 95), ("remark", "备注说明", 420)
        ]
        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.tree = ttk.Treeview(frame, columns=[x[0] for x in self.columns], show="headings", style="Custom.Treeview")
        for cid, name, width in self.columns:
            self.tree.heading(cid, text=name)
            anchor = tk.CENTER if cid in {"no", "network", "p1", "p2", "p3", "p4", "p5", "p6", "bulk"} else tk.W
            self.tree.column(cid, width=width, minwidth=45, anchor=anchor)
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
    def clean(v):
        return "" if v is None else str(v).replace("\ufeff", "").strip()

    @classmethod
    def norm(cls, v):
        return cls.clean(v).replace(" ", "").replace("　", "")

    @classmethod
    def getv(cls, row, aliases, default="-"):
        data = {cls.norm(k): cls.clean(v) for k, v in row.items() if k is not None}
        for a in aliases:
            v = data.get(cls.norm(a), "")
            if v != "":
                return v
        return default

    def read_csv(self, path):
        # 关键修复：一个 CSV 里可能有多张表、多个表头。不能只使用一次 DictReader。
        last_error = None
        for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                result, header = [], None
                with open(path, "r", encoding=enc, newline="") as f:
                    for raw in csv.reader(f):
                        row = [self.clean(x) for x in raw]
                        if not row or not any(row):
                            continue
                        first = self.norm(row[0])
                        if len(first) >= 5 and set(first) <= {"=", "-", "_"}:
                            continue
                        markers = {"品牌/系列", "系列分类", "系列", "型号", "机型及规格", "机型与规格"}
                        if any(self.norm(x) in markers for x in row):
                            header = row
                            continue
                        if not header:
                            continue
                        if len(row) < len(header):
                            row += [""] * (len(header) - len(row))
                        elif len(row) > len(header):
                            row = row[:len(header)]
                        result.append(dict(zip(header, row)))
                return result
            except (UnicodeDecodeError, UnicodeError) as e:
                last_error = e
        raise last_error or ValueError("无法读取 CSV 文件")

    def convert(self, row, brand):
        return {
            "source": brand,
            "series": self.getv(row, ["系列", "品牌/系列", "系列分类", "分类"], brand),
            "no": self.getv(row, ["序号", "编号"]),
            "model": self.getv(row, ["型号", "机型及规格", "机型与规格", "机型规格", "机型"], "未知"),
            "network": self.getv(row, ["网络型号", "网络制式型号", "网络制式", "网络型号/制式"], "/"),
            "p1": self.getv(row, ["开机靓好", "靓好", "开机屏好"]),
            "p2": self.getv(row, ["开机好屏", "开机好碎", "开机屏好外屏碎", "开机外屏碎", "好屏", "好碎"]),
            "p3": self.getv(row, ["开机碎屏", "开机屏坏未标", "开机屏坏", "碎屏"]),
            "p4": self.getv(row, ["开机坏配件", "开机压屏", "压屏", "坏配件"]),
            "p5": self.getv(row, ["不开机"]),
            "p6": self.getv(row, ["废板·整机", "废板-整机", "废板整机", "废板"]),
            "bulk": self.getv(row, ["统货", "开机无灯光", "无灯光"]),
            "remark": self.getv(row, ["备注", "备注说明"], "")
        }

    def load_all_data(self):
        query = self.search_var.get()
        self.all_data.clear()
        files = sorted(set(glob.glob(os.path.join(self.data_dir, "*.csv")) + glob.glob(os.path.join(self.data_dir, "*.CSV"))))
        loaded, failed = 0, []
        for path in files:
            try:
                brand = os.path.splitext(os.path.basename(path))[0]
                for row in self.read_csv(path):
                    model = self.getv(row, ["型号", "机型及规格", "机型与规格", "机型规格", "机型"], "")
                    if model and model not in {"型号", "机型及规格", "机型与规格"}:
                        self.all_data.append(self.convert(row, brand))
                loaded += 1
            except Exception as e:
                failed.append(f"{os.path.basename(path)}: {e}")
                print(f"加载失败 {path}: {e}")
        self.status_label.config(text=f"已加载 {loaded} 个数据文件，共 {len(self.all_data)} 行数据" + (f"，{len(failed)} 个失败" if failed else ""))
        self.search_var.set(query)
        self.do_search()
        if failed:
            messagebox.showwarning("部分数据读取失败", "以下文件读取失败：\n\n" + "\n".join(failed[:10]))

    def do_search(self):
        query = self.search_var.get().lower().strip()
        for item in self.tree.get_children():
            self.tree.delete(item)
        count = 0
        for d in self.all_data:
            text = " ".join(str(d.get(k, "")) for k, _, _ in self.columns).lower()
            if not query or query in text:
                self.tree.insert("", tk.END, values=tuple(d.get(k, "") for k, _, _ in self.columns), tags=("oddrow" if count % 2 == 0 else "evenrow",))
                count += 1
        base = self.status_label.cget("text").split(" | 当前搜索", 1)[0]
        self.status_label.config(text=base + (f" | 当前搜索 {count} 行" if query else ""))


if __name__ == "__main__":
    root = tk.Tk()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    app = PhonePriceSearchApp(root)
    root.mainloop()
