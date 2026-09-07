import csv
import glob
import json
import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# 尝试支持 openpyxl (用于直接读取/写入 Excel .xlsx)
try:
    import openpyxl

    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# 开启 Windows 高 DPI 适配
try:
    from ctypes import windll

    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

BRAND_SYNONYMS = {
    "小米": ["小米", "xiaomi", "红米", "redmi", "mi"],
    "红米": ["红米", "redmi", "小米", "xiaomi"],
    "苹果": ["苹果", "apple", "iphone", "ipad"],
    "华为": ["华为", "huawei"],
    "荣耀": ["荣耀", "honor"],
    "一加": ["一加", "oneplus", "1+"],
    "真我": ["真我", "realme"],
    "红魔": ["红魔", "redmagic", "努比亚", "nubia"],
    "努比亚": ["努比亚", "nubia", "红魔", "redmagic"],
    "谷歌": ["谷歌", "google", "pixel"],
    "摩托": ["摩托", "motorola", "moto"],
    "诺基亚": ["诺基亚", "nokia"],
    "三星": ["三星", "samsung", "galaxy"],
    "魅族": ["魅族", "meizu", "魅蓝"],
    "魅蓝": ["魅蓝", "魅族", "meizu"],
    "金立": ["金立", "gionee"],
    "酷派": ["酷派", "coolpad", "ivvi"],
    "中兴": ["中兴", "zte", "axon", "blade", "远航", "天机"],
    "步步高": ["步步高", "imoo"],
    "海信": ["海信", "hisense"],
    "华硕": ["华硕", "asus", "rog", "zenfone"],
    "美图": ["美图", "meitu"],
    "格力": ["格力", "gree"],
    "锤子": ["锤子", "坚果", "smartisan"],
    "坚果": ["坚果", "锤子", "smartisan"],
    "糖果": ["糖果", "sugar"],
    "国美": ["国美", "gome"],
    "联想": ["联想", "lenovo", "拯救者", "zuk", "乐檬"],
    "拯救者": ["拯救者", "lenovo", "联想"],
    "乐视": ["乐视", "letv", "leeco"],
    "移动": ["中国移动", "移动", "chinamobile"],
}


def clean_text(s):
    if not s:
        return ""
    return re.sub(r"[\s\-_+()（）/\[\]【】]+", "", str(s)).lower()


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class PhonePriceSearchApp:

    def __init__(self, root):
        self.root = root
        self.root.title("📱 手机回收价格系统 (变动标记 + 批量对账核价版)")
        self.root.geometry("1200x720")
        self.root.minsize(900, 550)

        self.base_dir = get_base_dir()
        self.data_dir = os.path.join(self.base_dir, "data")
        self.history_file = os.path.join(self.data_dir, "price_history.json")

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)

        self.all_data = []
        self.price_history = {}
        self.sort_column = None
        self.sort_reverse = False

        self._setup_ui()
        self.load_all_data()

    def _setup_ui(self):
        # 顶部搜索与操作栏
        top_frame = ttk.Frame(self.root, padding=(12, 10))
        top_frame.pack(fill=tk.X)

        ttk.Label(
            top_frame,
            text="🔍 搜索 (如: 小米 8 / 苹果 13)：",
            font=("微软雅黑", 10, "bold"),
        ).pack(side=tk.LEFT)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.do_search())
        self.search_entry = ttk.Entry(
            top_frame,
            textvariable=self.search_var,
            font=("微软雅黑", 10),
            width=24,
        )
        self.search_entry.pack(side=tk.LEFT, padx=5)

        clear_btn = ttk.Button(
            top_frame, text="清空", command=lambda: self.search_var.set("")
        )
        clear_btn.pack(side=tk.LEFT, padx=2)

        # 变动筛选框
        self.only_changed_var = tk.BooleanVar(value=False)
        self.only_changed_var.trace_add(
            "write", lambda *args: self.do_search()
        )
        ttk.Checkbutton(
            top_frame,
            text="🔥 只看价格有变动的机型",
            variable=self.only_changed_var,
        ).pack(side=tk.LEFT, padx=12)

        # 功能操作区
        btn_box = ttk.Frame(top_frame)
        btn_box.pack(side=tk.RIGHT)

        ttk.Button(
            btn_box,
            text="📋 批量导入清单自动核价",
            command=self.batch_price_inventory,
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            btn_box, text="📂 打开 data", command=self.open_data_folder
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_box, text="🔄 刷新", command=self.load_all_data).pack(
            side=tk.LEFT, padx=3
        )

        # 中部表格区
        table_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        table_frame.pack(fill=tk.BOTH, expand=True)

        self.columns = [
            ("source", "品牌/来源", 110),
            ("series", "系列", 90),
            ("model", "型号 / 版本", 190),
            ("price_good", "开机屏好/靓好", 110),
            ("price_screen_bad", "开机屏坏", 90),
            ("price_no_power", "不开机", 80),
            ("price_junk", "废板/整机", 80),
            ("fluctuation", "价格动态 / 变动", 130),
            ("remark", "关键备注 (可双击展开)", 260),
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

        # 配置涨价/跌价的颜色标签
        self.tree.tag_configure("price_up", foreground="#d90429")  # 红色标涨
        self.tree.tag_configure("price_down", foreground="#2a9d8f")  # 绿色标跌

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

        self.tree.bind("<Double-1>", self.show_detail)

        # 底部状态栏
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

    def open_data_folder(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.data_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.data_dir])
        else:
            subprocess.Popen(["xdg-open", self.data_dir])

    def load_all_data(self):
        """加载 CSV 数据与价格变动历史库"""
        self.all_data.clear()
        self.price_history.clear()

        # 加载价格变动日志
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.price_history = json.load(f)
            except Exception:
                self.price_history = {}

        csv_files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        if not csv_files:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.status_var.set(
                f"⚠️ 外部目录 [{self.data_dir}] 未找到任何 CSV 价格表！"
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
                        file_content = list(csv.DictReader(f))
                        break
                except Exception:
                    continue

            if not file_content:
                continue

            for row in file_content:
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
                ).strip()
                series = (
                    row.get("系列")
                    or row.get("品牌/系列")
                    or row.get("分类")
                    or file_name
                ).strip()
                p_good = (
                    row.get("开机屏好")
                    or row.get("开机靓好")
                    or row.get("开机屏好(无ID)")
                    or row.get("回收价格(元/点数)")
                    or "-"
                ).strip()
                p_s_bad = (
                    row.get("开机屏坏")
                    or row.get("开机屏坏(无ID)")
                    or row.get("开机屏坏/外碎")
                    or "-"
                ).strip()
                p_no_pwr = (row.get("不开机") or "-").strip()
                p_junk = (
                    row.get("废板-整机") or row.get("深板·整机") or "-"
                ).strip()
                remark = (row.get("备注") or "").strip()

                # 匹配价格变动标签
                key = f"{file_name}_{model}"
                history_info = self.price_history.get(key)
                fluctuation = "-"
                change_tag = ""

                if history_info:
                    old_p = history_info.get("old_price", "")
                    diff = history_info.get("diff", 0)
                    if diff > 0:
                        fluctuation = f"🔴 涨 {diff} (旧:{old_p})"
                        change_tag = "price_up"
                    elif diff < 0:
                        fluctuation = f"🟢 跌 {abs(diff)} (旧:{old_p})"
                        change_tag = "price_down"

                self.all_data.append(
                    {
                        "source": file_name,
                        "series": series,
                        "model": model,
                        "price_good": p_good,
                        "price_screen_bad": p_s_bad,
                        "price_no_power": p_no_pwr,
                        "price_junk": p_junk,
                        "fluctuation": fluctuation,
                        "change_tag": change_tag,
                        "remark": remark,
                        "raw_dict": row,
                    }
                )
            loaded_files += 1

        changed_count = sum(1 for x in self.all_data if x["change_tag"])
        self.status_var.set(
            f"✅ 载入 {loaded_files} 个表格，共 {len(self.all_data)} 条数据。其中检测到 {changed_count} 款机型价格有更新！"
        )
        self.do_search()

    def do_search(self):
        raw_query = self.search_var.get().strip()
        only_changed = self.only_changed_var.get()

        for item in self.tree.get_children():
            self.tree.delete(item)

        brand_terms, model_terms = self._parse_query(raw_query)
        matched_results = []

        for item in self.all_data:
            if only_changed and not item["change_tag"]:
                continue

            if not raw_query:
                matched_results.append((0, item))
                continue

            c_model = clean_text(item["model"])
            c_series = clean_text(item["series"])
            c_source = clean_text(item["source"])
            c_remark = clean_text(item["remark"])
            c_brand_scope = f"{c_source} {c_series}"

            # 1. 品牌范围匹配
            if brand_terms:
                brand_matched = False
                for _, syn_list in brand_terms:
                    if any(
                        syn in c_brand_scope or c_model.startswith(syn)
                        for syn in syn_list
                    ):
                        brand_matched = True
                        break
                if not brand_matched:
                    continue

            # 2. 型号多版本包容匹配
            model_matched = True
            score = 0
            for m_term in model_terms:
                if m_term in c_model:
                    if c_model == m_term:
                        score += 300
                    elif c_model.startswith(m_term) or c_model.endswith(m_term):
                        score += 180
                    else:
                        score += 100
                elif m_term in c_series or m_term in c_remark:
                    score += 40
                else:
                    model_matched = False
                    break

            if model_matched:
                score -= len(item["model"]) * 2
                matched_results.append((score, item))

        matched_results.sort(key=lambda x: x[0], reverse=True)

        for _, item in matched_results:
            tags = (item["change_tag"],) if item["change_tag"] else ()
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
                    item["fluctuation"],
                    item["remark"],
                ),
                tags=tags,
            )

    def _parse_query(self, query_str):
        raw_terms = [t for t in re.split(r"[\s,+，]+", query_str.strip()) if t]
        if not raw_terms:
            return [], []

        if len(raw_terms) == 1:
            single = raw_terms[0]
            for brand, syns in BRAND_SYNONYMS.items():
                for s in syns:
                    if single.lower().startswith(s) and len(single) > len(s):
                        raw_terms = [single[: len(s)], single[len(s) :]]
                        break

        brand_terms = []
        model_terms = []
        for t in raw_terms:
            t_clean = clean_text(t)
            is_brand = False
            for brand_key, syns in BRAND_SYNONYMS.items():
                if t_clean in [clean_text(x) for x in syns]:
                    brand_terms.append((t_clean, [clean_text(x) for x in syns]))
                    is_brand = True
                    break
            if not is_brand:
                model_terms.append(t_clean)
        return brand_terms, model_terms

    # ==================== 功能三：废旧手机清单批量核价 ====================
    def batch_price_inventory(self):
        """导入用户自己的旧手机表格 (Excel / CSV)，自动逐行对账并导出估价结果"""
        file_path = filedialog.askopenfilename(
            title="选择您的废旧手机清单表格",
            filetypes=[
                ("表格文件", "*.xlsx *.xls *.csv"),
                ("Excel表格", "*.xlsx *.xls"),
                ("CSV表格", "*.csv"),
            ],
        )
        if not file_path:
            return

        rows = []
        # 读取输入清单
        if file_path.lower().endswith((".xlsx", ".xls")):
            if not HAS_OPENPYXL:
                messagebox.showerror(
                    "缺少依赖",
                    "处理 Excel (.xlsx) 需要安装 openpyxl 库。\n请在终端执行：pip install openpyxl\n或者将表格先另存为 CSV 格式即可直接导入！",
                )
                return
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active
            headers = [str(cell.value or "").strip() for cell in ws[1]]
            for r in ws.iter_rows(min_row=2, values_only=True):
                rows.append(
                    {
                        headers[i]: str(r[i] or "").strip()
                        for i in range(len(headers))
                        if i < len(r)
                    }
                )
        else:
            encodings = ["utf-8-sig", "gb18030", "utf-8", "gbk"]
            for enc in encodings:
                try:
                    with open(file_path, "r", encoding=enc) as f:
                        rows = list(csv.DictReader(f))
                        break
                except Exception:
                    continue

        if not rows:
            messagebox.showwarning("警告", "未能从表格中读取到任何数据！")
            return

        # 智能寻找“型号/机型”列
        sample_keys = list(rows[0].keys())
        model_col = next(
            (
                k
                for k in sample_keys
                if any(x in k for x in ["型号", "机型", "设备", "名称", "品名"])
            ),
            None,
        )
        if not model_col:
            model_col = sample_keys[0]  # 默认取第一列

        # 开始批量比对核价
        matched_count = 0
        result_rows = []

        for r in rows:
            raw_input_model = r.get(model_col, "").strip()
            c_input = clean_text(raw_input_model)

            # 在全量回收库中智能寻找最佳匹配项
            best_match = None
            highest_score = -1

            for db_item in self.all_data:
                db_model = clean_text(db_item["model"])
                db_source = clean_text(db_item["source"])

                # 完全一致
                if c_input == db_model or c_input == f"{db_source}{db_model}":
                    best_match = db_item
                    highest_score = 1000
                    break

                # 包含匹配
                if db_model and (db_model in c_input or c_input in db_model):
                    score = 500 - abs(len(c_input) - len(db_model)) * 10
                    if score > highest_score:
                        highest_score = score
                        best_match = db_item

            row_out = dict(r)
            if best_match:
                row_out["回收匹配结果"] = (
                    f"【{best_match['source']}】{best_match['model']}"
                )
                row_out["开机屏好参考价"] = best_match["price_good"]
                row_out["开机屏坏参考价"] = best_match["price_screen_bad"]
                row_out["不开机参考价"] = best_match["price_no_power"]
                row_out["废板整机参考价"] = best_match["price_junk"]
                row_out["回收扣款备注细则"] = best_match["remark"]
                matched_count += 1
            else:
                row_out["回收匹配结果"] = "未匹配到对应机型"
                row_out["开机屏好参考价"] = "-"
                row_out["开机屏坏参考价"] = "-"
                row_out["不开机参考价"] = "-"
                row_out["废板整机参考价"] = "-"
                row_out["回收扣款备注细则"] = "-"

            result_rows.append(row_out)

        # 导出核价后的表格
        default_out_name = f"核价完成_{os.path.splitext(os.path.basename(file_path))[0]}_{datetime.now().strftime('%m%d_%H%M')}.xlsx"
        save_path = filedialog.asksaveasfilename(
            title="保存自动估价后的表格",
            initialfile=default_out_name,
            defaultextension=".xlsx" if HAS_OPENPYXL else ".csv",
            filetypes=[("Excel 表格", "*.xlsx")]
            if HAS_OPENPYXL
            else [("CSV 表格", "*.csv")],
        )
        if not save_path:
            return

        if save_path.lower().endswith(".xlsx") and HAS_OPENPYXL:
            wb_out = openpyxl.Workbook()
            ws_out = wb_out.active
            ws_out.title = "回收估价核算表"
            out_headers = list(result_rows[0].keys())
            ws_out.append(out_headers)
            for item in result_rows:
                ws_out.append([item.get(h, "") for h in out_headers])
            wb_out.save(save_path)
        else:
            with open(save_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(result_rows[0].keys()))
                writer.writeheader()
                writer.writerows(result_rows)

        messagebox.showinfo(
            "核价完成",
            f"🎉 批量估价已完成！\n总行数：{len(rows)} 行\n成功匹配：{matched_count} 款机型\n\n已成功保存至：\n{save_path}",
        )

    def sort_by_column(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
            self.sort_column = col

        def sort_key(item):
            val = item.get(col, "")
            try:
                return (0, float(val))
            except ValueError:
                return (1, str(val))

        self.all_data.sort(key=sort_key, reverse=self.sort_reverse)
        self.do_search()

    def show_detail(self, event):
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
        win.title(f"机型回收细则 - {model_name}")
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

        if matched_item.get("change_tag"):
            text_box.insert(
                tk.END,
                f"\n🔥 价格变动记录：{matched_item['fluctuation']}\n",
            )

        text_box.configure(state="disabled")
        ttk.Button(frame, text="确定", command=win.destroy).pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhonePriceSearchApp(root)
    root.mainloop()
