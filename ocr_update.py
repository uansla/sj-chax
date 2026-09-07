"""
ocr_update.py - 本地/云端图片价格识别与历史变动对比引擎
用法：
1. 把截屏图片存入 images/ 文件夹 (如 images/OPPO.jpg, images/Apple.jpg)
2. 运行: python ocr_update.py
3. 脚本会自动比对旧价格，更新 data/*.csv，并在 data/price_history.json 中生成涨跌记录！
"""

import csv
import json
import os
import re
from datetime import datetime

try:
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
except ImportError:
    engine = None

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(REPO_ROOT, "images")
DATA_DIR = os.path.join(REPO_ROOT, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


def load_existing_prices(csv_path):
    """读取已有表格价格用于对比"""
    prices = {}
    if not os.path.exists(csv_path):
        return prices
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                m = (row.get("型号") or "").strip()
                p = (row.get("开机屏好") or row.get("开机靓好") or "").strip()
                if m and p and p.isdigit():
                    prices[m] = int(p)
    except Exception:
        pass
    return prices


def process_image(img_path):
    if engine is None:
        print(
            "❌ 请先在终端安装 RapidOCR：pip install rapidocr_onnxruntime"
        )
        return

    brand_name = os.path.splitext(os.path.basename(img_path))[0]
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    old_prices = load_existing_prices(target_csv)

    print(f"🔍 正在智能识别图片: {img_path} ...")
    result, _ = engine(img_path)
    if not result:
        print(f"⚠️ 图片 {img_path} 未识别到文字。")
        return

    # 加载已有的全局历史记录
    history_data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            pass

    # 简易行归并与价格提取算法
    lines = [item[1].strip() for item in result if item[1].strip()]
    parsed_rows = []

    # 表头标准定义
    headers = [
        "系列",
        "序号",
        "型号",
        "开机屏好",
        "开机屏坏",
        "不开机",
        "废板-整机",
        "备注",
    ]

    # 正则提取带有数字价格的行
    idx = 1
    for text in lines:
        parts = re.split(r"[\s\t|,，]+", text)
        digits = [p for p in parts if p.isdigit()]

        # 如果这一行包含型号和多档报价
        if len(parts) >= 3 and len(digits) >= 1:
            model = parts[0]
            if model in ["型号", "序号", "开机屏好"]:
                continue

            p_good = digits[0] if len(digits) > 0 else "-"
            p_bad = digits[1] if len(digits) > 1 else p_good
            p_no_pwr = digits[2] if len(digits) > 2 else p_bad
            p_junk = digits[3] if len(digits) > 3 else p_no_pwr
            remark = parts[-1] if not parts[-1].isdigit() else ""

            # 比对价格变化
            if model in old_prices and p_good.isdigit():
                curr_price = int(p_good)
                prev_price = old_prices[model]
                if curr_price != prev_price:
                    diff = curr_price - prev_price
                    history_key = f"{brand_name}_{model}"
                    history_data[history_key] = {
                        "brand": brand_name,
                        "model": model,
                        "old_price": prev_price,
                        "new_price": curr_price,
                        "diff": diff,
                        "update_time": datetime.now().strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    }
                    print(
                        f"🔥 价格变动 detected: {model} {prev_price} -> {curr_price} ({'+' if diff > 0 else ''}{diff})"
                    )

            parsed_rows.append(
                {
                    "系列": brand_name,
                    "序号": str(idx),
                    "型号": model,
                    "开机屏好": p_good,
                    "开机屏坏": p_bad,
                    "不开机": p_no_pwr,
                    "废板-整机": p_junk,
                    "备注": remark,
                }
            )
            idx += 1

    if parsed_rows:
        with open(target_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(parsed_rows)
        print(f"✅ 已写入 {len(parsed_rows)} 条数据到 {target_csv}")

    # 保存价格变动历史库
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
    print("✅ 变动历史记录已同步保存至 data/price_history.json")


if __name__ == "__main__":
    if not os.listdir(IMAGE_DIR):
        print(f"提示：请先将长截图放入 '{IMAGE_DIR}' 目录下（例如 OPPO.jpg）")
    for img in os.listdir(IMAGE_DIR):
        if img.lower().endswith((".jpg", ".jpeg", ".png")):
            process_image(os.path.join(IMAGE_DIR, img))
