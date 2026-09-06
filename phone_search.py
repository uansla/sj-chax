import csv
import glob
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 开启 Windows 高 DPI 清晰度支持
try:
    from ctypes import windll

    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def get_app_dir():
    """获取程序所在的真实绝对路径（兼顾源码运行和 PyInstaller 打包运行）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class PhonePriceSearchApp:

    def __init__(self, root):
        self.root = root
        self.root.title("📱 手机回收价格秒查工具")
        self.root.geometry("1150x680")
        self.root.minsize(850, 500)

        # 确定数据目录优先级：程序目录下的 data 文件夹 -> 程序所在根目录
        self.base_dir = get_app_dir()
        self.data_dir = os.path.join(self.base_dir, "data")
        if not os.path.exists(self.data_dir):
            self.data_dir = self.base_dir

        self.all_data = []
        self.sort_column = None
        self.sort_reverse = False

        self._setup_ui()
        self.load_all_csv_files()

    def _setup_ui(self):
        # 1. 顶部操作工具栏
        top_frame = ttk.Frame(self.root, padding=(12, 10))
        top_frame.pack(fill=tk.X)

        ttk.Label(
            top_frame, text="🔍 搜索型号/品牌：", font=("微软雅黑", 10, "bold")
        ).pack(side=tk.LEFT)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.do_search())
        self.search_entry = ttk.Entry(
            top_frame,
            textvariable=self.search_var,
            font=("微软雅黑", 10),
            width=28,
        )
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.focus()

        clear_btn = ttk.Button(
            top_frame, text="清空", command=lambda: self.search_var.set("")
        )
        clear_btn.pack(side=tk.LEFT, padx=3)

        # 路径选择与重载按钮
        btn_box = ttk.Frame(top_frame)
        btn_box.pack(side=tk.RIGHT)

        ttk.Button(
            btn_box, text="📂 切换数据文件夹", command=self.choose_data_dir
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            btn_box, text="🔄 刷新数据", command=self.load_all_csv_files
        ).pack(side=tk.LEFT, padx=3)

        # 2. 中部数据表格
        table_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        table_frame.pack(fill=tk.BOTH, expand=True)

        self.columns = [
            ("source", "品牌/表格来源", 130),
            ("series", "系列", 100),
            ("model", "型号", 180),
            ("price_good", "开机屏好/靓好", 100),
            ("price_screen_bad", "开机屏坏", 90),
            ("price_no_power", "不开机", 90),
            ("price_junk", "废板/整机", 90),
            ("remark", "关键备注 (可双击展开)", 300),
        ]

        self.tree = ttk.Treeview(
            table_frame,
            columns=[col[0] for col in self.columns],
            show="headings",
            selectmode="browse",
        )

        for col_id, col_name, width in self.columns:
            self.tree.heading(
                col_id,
                text=col_name,
                command=lambda c=col_id: self.sort_by_column(c),
            )
            self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        hsb = ttk.Scrollbar(
            table_frame, orient=tk.HORIZONTAL, command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 绑定事件
        self.tree.bind("<Double-1>", self.show_detail)
        self.root.bind("<Escape>", lambda e: self.search_var.set(""))

        # 3. 底部状态栏
        self.status_var = tk.StringVar(value="准备就绪")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(8, 4),
            font=("微软雅黑", 9),
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def choose_data_dir(self):
        """支持手动指定存放 CSV 的文件夹"""
        chosen = filedialog.askdirectory(
            initialdir=self.data_dir, title="选择存放回收报价CSV的文件夹"
        )
        if chosen:
            self.data_dir = chosen
            self.load_all_csv_files()

    def load_all_csv_files(self):
        """自动扫描并载入指定文件夹下的所有 .csv 文件"""
        self.all_data.clear()

        # 查找目标文件夹中的所有 CSV 文件
        pattern = os.path.join(self.data_dir, "*.csv")
        csv_files = glob.glob(pattern)

        # 如果选中的目录没有，再回退查找当前脚本同级目录
        if not csv_files and self.data_dir != self.base_dir:
            csv_files = glob.glob(os.path.join(self.base_dir, "*.csv"))

        if not csv_files:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.status_var.set(
                f"⚠️ 在 '{self.data_dir}' 未找到任何 CSV 报价表文件，请放入表格后点击刷新。"
            )
            return

        encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
        loaded_files = 0

        for file_path in csv_files:
            file_name = (
                os.path.basename(file_path)
                .replace(".csv", "")
                .replace("_recycle_prices", "")
                .replace("回收价格", "")
            )

            file_content = None
            for enc in encodings:
                try:
                    with open(
                        file_path, "r", encoding=enc, errors="strict"
                    ) as f:
                        reader = csv.DictReader(f)
                        file_content = list(reader)
                        break
                except (UnicodeDecodeError, Exception):
                    continue

            if not file_content:
                continue

            for row in file_content:
                # 兼容多种不同品牌的表头字段
                model = (
                    row.get("型号")
                    or row.get("品名/型号")
                    or row.get("Google")
                    or row.get("诺基亚")
                    or row.get("点数")
                    or row.get("糖果")
                    or row.get("国美")
                    or row.get("点数系列")
                    or "未知型号"
                )
                series = (
                    row.get("系列")
                    or row.get("品牌/系列")
                    or row.get("分类")
                    or file_name
                )
                p_good = (
                    row.get("开机屏好")
                    or row.get("开机靓好")
                    or row.get("开机屏好(无ID)")
                    or row.get("回收价格(元/点数)")
                    or "-"
                )
                p_s_bad = (
                    row.get("开机屏坏")
                    or row.get("开机屏坏(无ID)")
                    or row.get("开机屏坏/外碎")
                    or "-"
                )
                p_no_pwr = row.get("不开机") or "-"
                p_junk = row.get("废板-整机") or row.get("深板·整机") or "-"
                remark = row.get("备注") or ""

                self.all_data.append(
                    {
                        "source": file_name,
                        "series": series.strip(),
                        "model": model.strip(),
                        "price_good": str(p_good).strip(),
                        "price_screen_bad": str(p_s_bad).strip(),
                        "price_no_power": str(p_no_pwr).strip(),
                        "price_junk": str(p_junk).strip(),
                        "remark": remark.strip(),
                        "raw_dict": row,
                    }
                )
            loaded_files += 1

        self.status_var.set(
            f"✅ 成功从 [{self.data_dir}] 载入 {loaded_files} 个文件，共计 {len(self.all_data)} 条机型价格数据。"
        )
        self.do_search()

    def do_search(self):
        """实时高效模糊匹配"""
        query = (
            self.search_var.get()
            .strip()
            .lower()
            .replace(" ", "")
            .replace("-", "")
        )

        for item in self.tree.get_children():
            self.tree.delete(item)

        matches = 0
        for item in self.all_data:
            # 搜索时将型号、系列、来源拼接后做全字符串模糊对比
            search_str = (
                (item["model"] + item["series"] + item["source"])
                .lower()
                .replace(" ", "")
                .replace("-", "")
            )

            if not query or query in search_str:
                self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        item["source"],
                        item["series"],
                        item["model"],
                        item["price_good"],
                        item["price_screen_bad"],
                        item["price_no_power"],
                        item["price_junk"],
                        item["remark"],
                    ),
                )
                matches += 1

        if query:
            self.status_var.set(
                f"🔍 关键词 '{self.search_var.get().strip()}'：找到 {matches} 个匹配机型 (双击行查看特例细则)"
            )

    def sort_by_column(self, col):
        """点击表头进行排序"""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
            self.sort_column = col

        # 尝试按数值排序，若不能转成数字则按字符串排序
        def sort_key(item):
            val = item.get(col, "")
            try:
                return (0, float(val))
            except ValueError:
                return (1, str(val))

        self.all_data.sort(key=sort_key, reverse=self.sort_reverse)
        self.do_search()

    def show_detail(self, event):
        """双击弹窗显示完整配置及扣款明细（比如苹果无ID、三星微老化档位等）"""
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        source_name, model_name = values[0], values[2]

        matched_item = next(
            (
                item
                for item in self.all_data
                if item["source"] == source_name and item["model"] == model_name
            ),
            None,
        )

        if not matched_item:
            return

        win = tk.Toplevel(self.root)
        win.title(f"报价与质检明细 - {model_name}")
        win.geometry("540x450")
        win.transient(self.root)

        frame = ttk.Frame(win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=f"【{source_name}】 {model_name}",
            font=("微软雅黑", 12, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))

        text_box = tk.Text(
            frame, wrap=tk.WORD, font=("Consolas", 10), padx=8, pady=8
        )
        text_box.pack(fill=tk.BOTH, expand=True)

        for k, v in matched_item["raw_dict"].items():
            if v and str(v).strip():
                text_box.insert(tk.END, f"• {k.ljust(15)} :  {v}\n")

        text_box.configure(state="disabled")
        ttk.Button(frame, text="确定", command=win.destroy).pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhonePriceSearchApp(root)
    root.mainloop()
