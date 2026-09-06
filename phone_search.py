import csv
import glob
import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

# 开启 Windows 高 DPI 清晰度
try:
    from ctypes import windll

    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 品牌同义词词典（中英文别名打通）
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
    """清理字符串：去除空白、横杠、括号并转小写"""
    if not s:
        return ""
    return re.sub(r"[\s\-_+()（）/\[\]【】]+", "", str(s)).lower()


def get_base_dir():
    """获取程序物理路径（兼容源码运行与打包 EXE）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class PhonePriceSearchApp:

    def __init__(self, root):
        self.root = root
        self.root.title("📱 手机回收价格秒查工具 (同系多版本聚拢版)")
        self.root.geometry("1150x680")
        self.root.minsize(850, 500)

        self.base_dir = get_base_dir()
        self.data_dir = os.path.join(self.base_dir, "data")
        if not os.path.exists(self.data_dir):
            try:
                os.makedirs(self.data_dir, exist_ok=True)
            except Exception:
                pass

        self.all_data = []
        self.sort_column = None
        self.sort_reverse = False

        self._setup_ui()
        self.load_all_csv_files()

    def _setup_ui(self):
        # 1. 顶部操作栏
        top_frame = ttk.Frame(self.root, padding=(12, 10))
        top_frame.pack(fill=tk.X)

        ttk.Label(
            top_frame,
            text="🔍 输入品牌与型号 (如: 小米 8 / 苹果 13)：",
            font=("微软雅黑", 10, "bold"),
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

        btn_box = ttk.Frame(top_frame)
        btn_box.pack(side=tk.RIGHT)

        ttk.Button(
            btn_box, text="📂 打开 data 文件夹", command=self.open_data_folder
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            btn_box, text="🔄 刷新表格数据", command=self.load_all_csv_files
        ).pack(side=tk.LEFT, padx=3)

        # 2. 中部数据表格
        table_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        table_frame.pack(fill=tk.BOTH, expand=True)

        self.columns = [
            ("source", "品牌/来源", 120),
            ("series", "系列", 100),
            ("model", "型号 / 版本", 210),
            ("price_good", "开机屏好/靓好", 100),
            ("price_screen_bad", "开机屏坏", 90),
            ("price_no_power", "不开机", 90),
            ("price_junk", "废板/整机", 90),
            ("remark", "关键备注 (可双击展开)", 290),
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

    def open_data_folder(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.data_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.data_dir])
        else:
            subprocess.Popen(["xdg-open", self.data_dir])

    def load_all_csv_files(self):
        self.all_data.clear()
        csv_files = glob.glob(os.path.join(self.data_dir, "*.csv"))

        if not csv_files:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.status_var.set(
                f"⚠️ 外部目录 [{self.data_dir}] 未找到 CSV 文件，请点击上方按钮放入后刷新。"
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
                except (UnicodeDecodeError, Exception):
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
            f"✅ 已载入 {loaded_files} 个表格文件，共 {len(self.all_data)} 条机型数据。支持输入 '品牌+型号' 联查所有版本。"
        )
        self.do_search()

    def _parse_query(self, query_str):
        """智能解析用户输入的搜索词，区分出'品牌词'与'型号词'"""
        raw_terms = [t for t in re.split(r"[\s,+，]+", query_str.strip()) if t]
        if not raw_terms:
            return [], []

        # 智能探测连写词（如“小米8a”自动拆成“小米”和“8a”）
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

    def do_search(self):
        """同系相对匹配算法：包容不同版本（青春版、探索版、旗舰版、无标记原版等）并层级排序"""
        raw_query = self.search_var.get().strip()

        for item in self.tree.get_children():
            self.tree.delete(item)

        if not raw_query:
            for item in self.all_data:
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
            self.status_var.set(f"当前展示全部 {len(self.all_data)} 条机型数据。")
            return

        brand_terms, model_terms = self._parse_query(raw_query)
        matched_results = []

        for item in self.all_data:
            c_model = clean_text(item["model"])
            c_series = clean_text(item["series"])
            c_source = clean_text(item["source"])
            c_remark = clean_text(item["remark"])
            c_brand_scope = f"{c_source} {c_series}"

            # 1. 品牌范围匹配校验
            brand_matched = True
            if brand_terms:
                for _, syn_list in brand_terms:
                    # 只要品牌候选词出现在 来源、系列、或型号前缀 中即算通过
                    if not any(
                        syn in c_brand_scope or c_model.startswith(syn)
                        for syn in syn_list
                    ):
                        brand_matched = False
                        break

            if not brand_matched:
                continue

            # 2. 型号与衍生版本包容性匹配校验
            model_matched = True
            score = 0

            for m_term in model_terms:
                # 检查型号关键字是否包含在型号字段中（相对模糊匹配，允许后缀如“青春版”、“Pro”等）
                if m_term in c_model:
                    if c_model == m_term:
                        score += 300  # 基础版/未加标记原版，最高优先级
                    elif c_model.startswith(m_term) or c_model.endswith(m_term):
                        score += 180  # 衍生前缀/后缀版本 (如 8A青春版、红米8A)
                    else:
                        score += 100  # 型号中包含
                elif m_term in c_series or m_term in c_remark:
                    score += 40  # 系列或备注中包含
                else:
                    model_matched = False
                    break

            if model_matched:
                # 名字越精简越靠前（例如“小米8”会排在“小米8青春版”前面，形成主版本领头、衍生版跟随的直观排布）
                score -= len(item["model"]) * 2
                matched_results.append((score, item))

        # 评分降序排列
        matched_results.sort(key=lambda x: x[0], reverse=True)

        for _, item in matched_results:
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

        self.status_var.set(
            f"🔍 找到 {len(matched_results)} 个相关型号及细分版本 (同型号各版本已自动聚拢，便于对比出价)"
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
        win.title(f"报价与质检细则 - {model_name}")
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
