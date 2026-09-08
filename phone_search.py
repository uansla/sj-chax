import csv
import glob
import json
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

class PhonePriceSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数码回收价格秒查工具 - 10列专业版")
        self.root.geometry("1300x750")
        
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.all_data = []
        
        self._setup_ui()
        self.load_all_data()

    def _setup_ui(self):
        # 搜索栏
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="关键词搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.do_search())
        ttk.Entry(top_frame, textvariable=self.search_var, width=40).pack(side=tk.LEFT, padx=10)
        ttk.Button(top_frame, text="刷新数据", command=self.load_all_data).pack(side=tk.LEFT)

        # 表格列定义 (10列)
        self.columns = [
            ("source", "品牌", 80),
            ("series", "系列", 100),
            ("model", "型号/规格", 200),
            ("p1", "开机靓好", 80),
            ("p2", "开机好碎", 80),
            ("p3", "开机碎屏", 80),
            ("p4", "开机压屏", 80),
            ("p5", "不开机", 80),
            ("p6", "废板-整机", 80),
            ("remark", "备注", 250)
        ]

        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(table_frame, columns=[c[0] for c in self.columns], show="headings")
        
        for col_id, col_name, width in self.columns:
            self.tree.heading(col_id, text=col_name)
            self.tree.column(col_id, width=width, anchor=tk.W)

        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def load_all_data(self):
        self.all_data.clear()
        files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        
        for f_path in files:
            brand = os.path.basename(f_path).replace(".csv", "")
            try:
                with open(f_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.all_data.append({
                            "source": brand,
                            "series": row.get("系列", brand),
                            "model": row.get("型号", "未知"),
                            "p1": row.get("开机靓好") or row.get("开机屏好") or "-",
                            "p2": row.get("开机好碎") or row.get("开机屏坏") or "-",
                            "p3": row.get("开机碎屏") or "-",
                            "p4": row.get("开机压屏") or "-",
                            "p5": row.get("不开机") or "-",
                            "p6": row.get("废板-整机") or "-",
                            "remark": row.get("备注", "")
                        })
            except Exception as e:
                print(f"读取文件失败 {f_path}: {e}")
        
        self.do_search()

    def do_search(self):
        query = self.search_var.get().lower().strip()
        for item in self.tree.get_children(): self.tree.delete(item)
        
        for d in self.all_data:
            if not query or query in d['model'].lower() or query in d['source'].lower():
                self.tree.insert("", tk.END, values=(
                    d['source'], d['series'], d['model'], d['p1'], d['p2'], 
                    d['p3'], d['p4'], d['p5'], d['p6'], d['remark']
                ))

if __name__ == "__main__":
    root = tk.Tk()
    app = PhonePriceSearchApp(root)
    root.mainloop()
