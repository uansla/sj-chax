import csv
import glob
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess

# 开启 Windows 高分屏缩放优化 (防止模糊)
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

class PhonePriceSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数码回收价格秒查工具 - 专业大字版")
        self.root.geometry("1500x850")

        # --- 路径逻辑 ---
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.data_dir = os.path.join(self.base_dir, "data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.all_data = []
        
        # --- 样式配置 ---
        self.style = ttk.Style()
        self.style.theme_use("clam") # 使用 clam 主题以获得更好的样式自定义支持
        
        # 配置全局字体
        self.font_main = ("微软雅黑", 12)
        self.font_bold = ("微软雅黑", 12, "bold")
        self.font_header = ("微软雅黑", 13, "bold")
        self.font_search = ("微软雅黑", 14)

        # 自定义 Treeview 样式
        self.style.configure("Custom.Treeview", 
                             font=self.font_main, 
                             rowheight=35, # 大幅增加行高
                             background="white",
                             foreground="black",
                             fieldbackground="white")
        
        self.style.configure("Custom.Treeview.Heading", 
                             font=self.font_header, 
                             background="#eeeeee")
        
        # 选中行的颜色
        self.style.map("Custom.Treeview", 
                       background=[('selected', '#0078d7')],
                       foreground=[('selected', 'white')])

        self._setup_ui()
        self.load_all_data()

    def _setup_ui(self):
        # 顶部工具栏
        top_frame = ttk.Frame(self.root, padding=15)
        top_frame.pack(fill=tk.X)

        # 1. 搜索框
        ttk.Label(top_frame, text="🔍 搜索型号/品牌:", font=self.font_header).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.do_search())
        
        # 设置搜索框字体大一些
        self.search_entry = tk.Entry(top_frame, textvariable=self.search_var, 
                                     font=self.font_search, width=40, relief="solid", borderwidth=1)
        self.search_entry.pack(side=tk.LEFT, padx=15, ipady=3)
        
        # 2. 按钮 (加大字号)
        btn_refresh = tk.Button(top_frame, text="🔄 刷新数据", command=self.load_all_data,
                                font=self.font_main, bg="#f0f0f0", padx=10)
        btn_refresh.pack(side=tk.LEFT, padx=5)
        
        btn_folder = tk.Button(top_frame, text="📂 打开数据夹", command=self.open_data_folder,
                               font=self.font_main, bg="#f0f0f0", padx=10)
        btn_folder.pack(side=tk.LEFT, padx=5)

        # 右侧统计
        self.status_label = ttk.Label(top_frame, text="", font=self.font_main, foreground="#666666")
        self.status_label.pack(side=tk.RIGHT)

        # 表格区域
        self.columns = [
            ("source", "品牌", 90),
            ("series", "系列", 110),
            ("model", "机型规格 (搜索结果)", 320),
            ("p1", "靓好", 100),
            ("p2", "好碎", 100),
            ("p3", "碎屏", 100),
            ("p4", "压屏", 100),
            ("p5", "不开机", 100),
            ("p6", "废板", 100),
            ("remark", "备注说明", 300)
        ]

        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        self.tree = ttk.Treeview(table_frame, columns=[c[0] for c in self.columns], 
                                 show="headings", style="Custom.Treeview")
        
        # 配置列标题和宽度
        for col_id, col_name, width in self.columns:
            self.tree.heading(col_id, text=col_name)
            # 价格列居中对齐，机型和备注左对齐
            align = tk.CENTER if col_id.startswith('p') else tk.W
            self.tree.column(col_id, width=width, anchor=align)

        # 滚动条
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 隔行变色配置
        self.tree.tag_configure('oddrow', background='#f9f9f9')
        self.tree.tag_configure('evenrow', background='#ffffff')
        # 特别加粗价格列 (通过 tag 整体设置较难，这里通过数据逻辑区分)

    def open_data_folder(self):
        try:
            if sys.platform == "win32":
                os.startfile(self.data_dir)
            else:
                subprocess.Popen(["open", self.data_dir])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {e}")

    def load_all_data(self):
        self.all_data.clear()
        csv_files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        
        count = 0
        for f_path in csv_files:
            brand = os.path.basename(f_path).replace(".csv", "")
            try:
                try:
                    with open(f_path, "r", encoding="utf-8-sig") as f:
                        reader = list(csv.DictReader(f))
                except:
                    with open(f_path, "r", encoding="gbk") as f:
                        reader = list(csv.DictReader(f))

                for row in reader:
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
                print(f"加载失败 {f_path}: {e}")
        
        self.status_label.config(text=f"已加载 {count} 个品牌, 共 {len(self.all_data)} 行数据")
        self.do_search()

    def do_search(self):
        query = self.search_var.get().lower().strip()
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        row_idx = 0
        for d in self.all_data:
            if not query or query in d['model'].lower() or query in d['source'].lower() or query in d['series'].lower():
                tag = 'oddrow' if row_idx % 2 == 0 else 'evenrow'
                self.tree.insert("", tk.END, values=(
                    d['source'], d['series'], d['model'],
                    d['p1'], d['p2'], d['p3'], d['p4'], d['p5'], d['p6'],
                    d['remark']
                ), tags=(tag,))
                row_idx += 1

if __name__ == "__main__":
    root = tk.Tk()
    # 强制窗口在最前弹出一次，然后恢复正常
    root.lift()
    root.attributes('-topmost', True)
    root.after(500, lambda: root.attributes('-topmost', False))
    
    app = PhonePriceSearchApp(root)
    root.mainloop()
