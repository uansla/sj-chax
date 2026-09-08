import csv
import glob
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess

# 开启 Windows 高分屏缩放优化
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

class PhonePriceSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数码回收价格秒查工具 - 10列专业版")
        self.root.geometry("1400x750")

        # --- 核心路径逻辑修正 ---
        if getattr(sys, 'frozen', False):
            # 如果是打包后的 EXE 运行，路径为 EXE 所在目录
            self.base_dir = os.path.dirname(sys.executable)
        else:
            # 如果是脚本运行，路径为脚本所在目录
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.data_dir = os.path.join(self.base_dir, "data")
        
        # 自动创建 data 文件夹（如果不存在）
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.all_data = []
        self._setup_ui()
        self.load_all_data()

    def _setup_ui(self):
        # 顶部工具栏
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        # 1. 搜索框
        ttk.Label(top_frame, text="关键词搜索:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.do_search())
        self.search_entry = ttk.Entry(top_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=10)
        
        # 2. 刷新按钮
        ttk.Button(top_frame, text="🔄 刷新/重载数据", command=self.load_all_data).pack(side=tk.LEFT, padx=5)
        
        # 3. 打开文件夹按钮
        ttk.Button(top_frame, text="📂 打开数据文件夹", command=self.open_data_folder).pack(side=tk.LEFT, padx=5)

        # 提示文本
        self.status_label = ttk.Label(top_frame, text="", foreground="blue")
        self.status_label.pack(side=tk.RIGHT)

        # 表格区域
        self.columns = [
            ("source", "品牌/文件", 80),
            ("series", "系列", 100),
            ("model", "机型/规格配置", 280),
            ("p1", "开机靓好", 85),
            ("p2", "开机好碎", 85),
            ("p3", "开机碎屏", 85),
            ("p4", "开机压屏", 85),
            ("p5", "不开机", 85),
            ("p6", "废板-整机", 85),
            ("remark", "备注", 250)
        ]

        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.tree = ttk.Treeview(table_frame, columns=[c[0] for c in self.columns], show="headings")
        for col_id, col_name, width in self.columns:
            self.tree.heading(col_id, text=col_name)
            self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

    def open_data_folder(self):
        """打开 data 文件夹，方便用户放入新的 CSV"""
        try:
            if sys.platform == "win32":
                os.startfile(self.data_dir)
            else:
                subprocess.Popen(["open", self.data_dir])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {e}")

    def load_all_data(self):
        """扫描 data 目录下的所有 CSV 并加载"""
        self.all_data.clear()
        csv_files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        
        count = 0
        for f_path in csv_files:
            brand = os.path.basename(f_path).replace(".csv", "")
            try:
                # 依次尝试 utf-8-sig 和 gbk 编码，解决不同来源 CSV 的乱码问题
                try:
                    with open(f_path, "r", encoding="utf-8-sig") as f:
                        reader = list(csv.DictReader(f))
                except:
                    with open(f_path, "r", encoding="gbk") as f:
                        reader = list(csv.DictReader(f))

                for row in reader:
                    # 适配 10 列标准，同时兼容各种旧表头名
                    self.all_data.append({
                        "source": brand,
                        "series": row.get("系列") or brand,
                        "model": row.get("型号") or row.get("机型及配置") or "未知",
                        "p1": row.get("开机靓好") or row.get("开机屏好") or "-",
                        "p2": row.get("开机好碎") or row.get("开机屏坏") or "-",
                        "p3": row.get("开机碎屏") or "-",
                        "p4": row.get("开机压屏") or "-",
                        "p5": row.get("不开机") or "-",
                        "p6": row.get("废板-整机") or "-",
                        "remark": row.get("备注") or ""
                    })
                count += 1
            except Exception as e:
                print(f"文件 {f_path} 加载失败: {e}")
        
        self.status_label.config(text=f"已加载 {count} 个表格, 共 {len(self.all_data)} 条数据")
        self.do_search()

    def do_search(self):
        query = self.search_var.get().lower().strip()
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for d in self.all_data:
            if not query or query in d['model'].lower() or query in d['source'].lower() or query in d['series'].lower():
                self.tree.insert("", tk.END, values=(
                    d['source'], d['series'], d['model'],
                    d['p1'], d['p2'], d['p3'], d['p4'], d['p5'], d['p6'],
                    d['remark']
                ))

if __name__ == "__main__":
    root = tk.Tk()
    app = PhonePriceSearchApp(root)
    root.mainloop()
