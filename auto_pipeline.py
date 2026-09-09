import csv
import hashlib
import json
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from PIL import Image

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

# 与查询程序兼容的完整字段。OCR 无法识别的字段保持为空，避免查询程序丢列。
CSV_HEADERS = [
    "系列", "序号", "型号", "网络制式型号", "开机靓好", "开机好碎",
    "开机碎屏", "开机坏配件", "不开机", "废板·整机", "统货", "备注"
]

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}


def get_file_md5(filepath):
    if not os.path.exists(filepath):
        return ""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def crawl_and_download_images():
    print(f"[{datetime.now()}] 正在抓取官网海报图片...")
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        res = session.get(INDEX_URL, timeout=20)
        res.raise_for_status()
        res.encoding = res.apparent_encoding
    except requests.RequestException as e:
        print(f"网络错误: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    downloaded_images = []
    known_brands = [
        "Apple", "Huawei", "Honor", "OPPO", "VIVO", "Xiaomi", "Redmi",
        "Samsung", "OnePlus", "Realme", "Meizu"
    ]

    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("data-original") or img.get("src") or ""
        alt = img.get("alt") or img.get("title") or ""
        if not src or any(x in src.lower() for x in ("logo", "icon", "banner")):
            continue
        if not src.startswith(("http://", "https://")):
            src = requests.compat.urljoin(BASE_URL, src)

        brand_name = "Other"
        for brand in known_brands:
            if brand.lower() in (alt + src).lower():
                brand_name = brand
                break

        save_path = os.path.join(IMAGE_DIR, f"{brand_name}.jpg")
        try:
            img_res = session.get(src, timeout=30)
            img_res.raise_for_status()
            new_md5 = hashlib.md5(img_res.content).hexdigest()
            if new_md5 != get_file_md5(save_path):
                with open(save_path, "wb") as f:
                    f.write(img_res.content)
                downloaded_images.append((brand_name, save_path))
                print(f"下载新海报: {brand_name}.jpg")
        except requests.RequestException as e:
            print(f"图片下载失败 {src}: {e}")

    return downloaded_images


def slice_and_ocr_long_image(image_path, slice_height=2000):
    if ocr_engine is None:
        raise RuntimeError("未安装 rapidocr_onnxruntime，请先执行 pip install -r requirements.txt")

    all_ocr_lines = []
    with Image.open(image_path) as img:
        width, height = img.size
        step = max(1, slice_height - 100)
        y = 0
        while y < height:
            box_bottom = min(y + slice_height, height)
            slice_img = img.crop((0, y, width, box_bottom))
            result, _ = ocr_engine(slice_img)
            if result:
                for item in result:
                    if len(item) >= 2 and str(item[1]).strip():
                        all_ocr_lines.append(str(item[1]).strip())
            y += step
    return all_ocr_lines


def parse_and_sync_prices(brand_name, ocr_lines):
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    parsed_rows = []
    idx = 1

    history_data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            history_data = {}

    for text in ocr_lines:
        parts = re.split(r"[\s\t|,，/]+", text)
        digits = [p for p in parts if re.fullmatch(r"\d+(?:\.\d+)?", p)]
        if len(parts) < 2 or not digits:
            continue

        model = parts[0].strip()
        if model in {"型号", "序号", "机型", "开机靓好"}:
            continue

        prices = [digits[i] if i < len(digits) else digits[-1] for i in range(6)]
        remark = parts[-1] if not re.fullmatch(r"\d+(?:\.\d+)?", parts[-1]) else ""

        parsed_rows.append({
            "系列": brand_name,
            "序号": str(idx),
            "型号": model,
            "网络制式型号": "",
            "开机靓好": prices[0],
            "开机好碎": prices[1],
            "开机碎屏": prices[2],
            "开机坏配件": prices[3],
            "不开机": prices[4],
            "废板·整机": prices[5],
            "统货": "",
            "备注": remark,
        })
        idx += 1

    # OCR 结果为空时绝不覆盖已有数据，避免网络/OCR 异常导致整张价格表被清空。
    if not parsed_rows:
        print(f"⚠️ {brand_name} 未得到有效价格行，保留原 CSV，不执行覆盖。")
        return

    with open(target_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(parsed_rows)
    print(f"CSV同步完成: {brand_name}.csv, 共 {len(parsed_rows)} 行")

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)


def run_pipeline():
    if ocr_engine is None:
        raise RuntimeError("未安装 rapidocr_onnxruntime，请先执行 pip install -r requirements.txt")

    updated = crawl_and_download_images()
    if updated:
        process_list = updated
    else:
        process_list = [
            (os.path.splitext(name)[0], os.path.join(IMAGE_DIR, name))
            for name in os.listdir(IMAGE_DIR)
            if name.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

    if not process_list:
        print("没有可处理的图片，流水线结束。")
        return

    for brand, img_path in process_list:
        try:
            lines = slice_and_ocr_long_image(img_path)
            parse_and_sync_prices(brand, lines)
        except Exception as e:
            print(f"处理 {brand} 失败: {e}")


if __name__ == "__main__":
    run_pipeline()
