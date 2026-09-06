import csv
import glob
import os
import tkinter as tk
from tkinter import messagebox, ttk


class PhonePriceSearchApp:

    def __init__(self, root):
        self.root = root
        self.root.title("📱 手机回收价格快速查询工具")
        self.root.geometry("1100x650")
        self.root.minsize(800, 500)

        # 数据存储
        self.all_data = []

        # 界面初始化
        self._setup_ui()

        # 加载数据
        self.load_all_csv_files()

    def _setup_ui(self):
        # 顶部搜索栏
        top_frame = ttk.Frame(self.root, padding=12)
        top_frame.pack(fill=tk.X)

        ttk.Label(
            top_frame, text="🔍 搜索机型/品牌：", font=("微软雅黑", 11, "bold")
        ).pack(side=tk.LEFT)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.do_search())
        self.search_entry = ttk.Entry(
            top_frame,
            textvariable=self.search_var,
            font=("微软雅黑", 11),
            width=30,
        )
        self.search_entry.pack(side=tk.LEFT, padx=6)
        self.search_entry.focus()

        clear_btn = ttk.Button(
            top_frame, text="清空", command=lambda: self.search_var.set("")
        )
        clear_btn.pack(side=tk.LEFT, padx=4)

        reload_btn = ttk.Button(
            top_frame, text="🔄 重新加载表格", command=self.load_all_csv_files
        )
        reload_btn.pack(side=tk.RIGHT)

        # 中部表格区域
        table_frame = ttk.Frame(self.root, padding=10)
        table_frame.pack(fill=tk.BOTH, expand=True)

        # 核心展示列
        self.columns = [
            ("source", "品牌/来源", 120),
            ("series", "系列", 90),
            ("model", "型号", 180),
            ("price_good", "开机屏好/靓好", 100),
            ("price_screen_bad", "开机屏坏", 90),
            ("price_no_power", "不开机", 90),
            ("price_junk", "废板/整机", 90),
            ("remark", "关键备注", 260),
        ]

        self.tree = ttk.Treeview(
            table_frame,
            columns=[col[0] for col in self.columns],
            show="headings",
            selectmode="browse",
        )

        for col_id, col_name, width in self.columns:
            self.tree.heading(col_id, text=col_name, anchor=tk.W)
            self.tree.column(col_id, width=width, anchor=tk.W)

        # 滚动条
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

        # 双击弹窗查看该行全部明细
        self.tree.bind("<Double-1>", self.show_detail)

        # 底部状态栏
        self.status_var = tk.StringVar(value="正在初始化...")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=5,
            font=("微软雅黑", 9),
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def load_all_csv_files(self):
        """遍历当前目录或 ./data 目录下的所有 CSV 文件"""
        self.all_data.clear()
        csv_files = glob.glob("*.csv") + glob.glob("data/*.csv")
        csv_files = list(set(csv_files))  # 去重

        if not csv_files:
            self.status_var.set(
                "⚠️ 未找到任何 .csv 文件！请将整理好的报价表格放到程序同一目录下或 data 文件夹内。"
            )
            return

        loaded_count = 0
        encodings = ["utf-8-sig", "utf-8", "gbk", "gb18030"]

        for file_path in csv_files:
            file_name = (
                os.path.basename(file_path)
                .replace(".csv", "")
                .replace("_recycle_prices", "")
                .replace("回收价格", "")
            )

            # 尝试不同编码读取
            file_content = None
            for enc in encodings:
                try:
                    with open(
                        file_path, "r", encoding=enc, errors="strict"
                    ) as f:
                        file_content = list(csv.DictReader(f))
                        break
                except UnicodeDecodeError:
                    continue

            if file_content is None:
                continue

            for row in file_content:
                # 提取标准字段兼容处理
                model = (
                    row.get("型号")
                    or row.get("品名/型号")
                    or row.get("Google")
                    or row.get("诺基亚")
                    or row.get("点数")
                    or row.get("糖果")
                    or row.get("国美")
                    or "未知型号"
                )
                series = (
                    row.get("系列")
                    or row.get("品牌/系列")
                    or row.get("分类")
                    or "-"
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

                item = {
                    "source": file_name,
                    "series": series.strip(),
                    "model": model.strip(),
                    "price_good": str(p_good).strip(),
                    "price_screen_bad": str(p_s_bad).strip(),
                    "price_no_power": str(p_no_pwr).strip(),
                    "price_junk": str(p_junk).strip(),
                    "remark": remark.strip(),
                    "raw_dict": row,  # 保留全部原始列用于双击弹窗查看
                }
                self.all_data.append(item)
            loaded_count += 1

        self.status_var.set(
            f"✅ 已成功载入 {loaded_count} 个报价表，共计 {len(self.all_data)} 条机型数据。支持输入型号即时检索，双击行可查看详细配件要求与细则。"
        )
        self.do_search()

    def do_search(self):
        query = (
            self.search_var.get()
            .strip()
            .lower()
            .replace(" ", "")
            .replace("-", "")
        )

        # 清空当前列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        matches = 0
        for item in self.all_data:
            # 综合多维度模糊搜索（型号、系列、来源）
            target_str = (
                (item["model"] + item["series"] + item["source"])
                .lower()
                .replace(" ", "")
                .replace("-", "")
            )

            if not query or query in target_str:
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
                    tags=(str(len(self.tree.get_children())),),
                )
                matches += 1

        if query:
            self.status_var.set(f"🔍 搜索关键词：'{query}'，找到 {matches} 个匹配结果")

    def show_detail(self, event):
        """双击查看该机型所有特殊细则（如苹果无ID板、三星大/小老化、不带电池价等）"""
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        model_name = values[2]

        # 找到对应原始项
        matched_item = None
        for item in self.all_data:
            if item["source"] == values[0] and item["model"] == model_name:
                matched_item = item
                break

        if not matched_item:
            return

        # 弹窗显示详情
        detail_win = tk.Toplevel(self.root)
        detail_win.title(f"机型报价详情 - {model_name}")
        detail_win.geometry("520x420")
        detail_win.transient(self.root)

        txt_frame = ttk.Frame(detail_win, padding=12)
        txt_frame.pack(fill=tk.BOTH, expand=True)

        title_lbl = ttk.Label(
            txt_frame,
            text=f"【{matched_item['source']}】 {model_name}",
            font=("微软雅黑", 12, "bold"),
        )
        title_lbl.pack(anchor=tk.W, pady=(0, 10))

        detail_text = tk.Text(
            txt_frame, wrap=tk.WORD, font=("Consolas", 10), padx=8, pady=8
        )
        detail_text.pack(fill=tk.BOTH, expand=True)

        for k, v in matched_item["raw_dict"].items():
            if v and str(v).strip():
                detail_text.insert(tk.END, f"• {k.ljust(16)} :  {v}\n")

        detail_text.configure(state="disabled")

        close_btn = ttk.Button(
            detail_win, text="关闭", command=detail_win.destroy
        )
        close_btn.pack(pady=8)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhonePriceSearchApp(root)
    root.mainloop()
