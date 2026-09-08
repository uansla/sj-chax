import csv
import hashlib
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from PIL import Image
import requests

try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
except ImportError:
    ocr_engine = None

BASE_URL = "https://www.smhsw.com"
INDEX_URL = "https://www.smhsw.com/index/index/index.html"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(REPO_ROOT, "images")
DATA_DIR = os.path.join(REPO_ROOT, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")

# 定义标准的 10 列字段
HEADERS = ["系列", "序号", "型号", "开机靓好", "开机好碎", "开机碎屏", "开机压屏", "不开机", "废板-整机", "备注"]

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_existing_brand_prices(brand_name):
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    prices = {}
    if os.path.exists(target_csv):
        try:
            with open(target_csv, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    m = row.get("型号", "").strip()
                    p = row.get("开机靓好") or row.get("开机屏好") or ""
                    if m and p and str(p).replace('.','').isdigit():
                        prices[m] = float(p)
        except: pass
    return prices

def parse_and_update_csv(brand_name, raw_lines, history_data):
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    old_prices = get_existing_brand_prices(brand_name)
    parsed_rows = []
    idx = 1

    for text in raw_lines:
        # 使用正则拆分文字和数字
        parts = re.split(r"[\s\t|,，/]+", text)
        digits = [p for p in parts if re.match(r"^\d+(\.\d+)?$", p)]
        
        if len(parts) >= 2 and len(digits) >= 1:
            model = parts[0]
            if model in ["型号", "序号", "机型", "开机靓好"]: continue

            # 填充 6 个价格位 (靓好, 好碎, 碎屏, 压屏, 不开机, 废板)
            p_v = [digits[i] if i < len(digits) else digits[-1] for i in range(6)]
            remark = parts[-1] if not re.match(r"^\d+(\.\d+)?$", parts[-1]) else ""

            # 记录价格变动
            if model in old_prices:
                new_p = float(p_v[0])
                if new_p != old_prices[model]:
                    history_data[f"{brand_name}_{model}"] = {
                        "brand": brand_name, "model": model, "old": old_prices[model], 
                        "new": new_p, "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }

            parsed_rows.append({
                "系列": brand_name, "序号": str(idx), "型号": model,
                "开机靓好": p_v[0], "开机好碎": p_v[1], "开机碎屏": p_v[2],
                "开机压屏": p_v[3], "不开机": p_v[4], "废板-整机": p_v[5], "备注": remark
            })
            idx += 1

    if parsed_rows:
        with open(target_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(parsed_rows)
        print(f"✅ 更新成功: {brand_name}.csv ({len(parsed_rows)} 行)")

# 其余下载和切片 OCR 逻辑保持不变...
