"""
update_prices.py
Automated Price Fetcher & OCR Sync Engine for Phone Recycling Data.
- Scrapes daily quotation poster images and web tables from smhsw.com.
- Performs slice-based OCR on ultra-tall images (tens of thousands of pixels).
- Compares new prices against existing CSV files in data/.
- Automatically records price fluctuations into data/price_history.json.
- Keeps Chinese content inside CSV files while keeping code/logs in English.
"""

import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from PIL import Image
import requests

# Optional RapidOCR engine for image processing
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

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

# Supported brand detection list
KNOWN_BRANDS = [
    "Apple",
    "Huawei",
    "Honor",
    "OPPO",
    "VIVO",
    "Xiaomi",
    "Redmi",
    "Samsung",
    "OnePlus",
    "Realme",
    "Meizu",
    "ZTE",
    "Lenovo",
    "Nubia",
    "Nokia",
    "Motorola",
    "Google",
    "Gionee",
    "Coolpad",
    "HTC",
    "TCL",
    "Meitu",
    "Sugar",
    "Hisense",
    "DOOV",
    "Gree",
    "Smartisan",
    "ChinaMobile",
    "苹果",
    "华为",
    "荣耀",
    "小米",
    "红米",
    "三星",
    "一加",
    "真我",
    "魅族",
    "中兴",
    "联想",
    "努比亚",
    "诺基亚",
    "摩托罗拉",
    "谷歌",
    "金立",
    "酷派",
    "美图",
    "糖果",
    "海信",
    "朵唯",
    "格力",
    "锤子",
    "移动",
]


def get_file_md5(filepath):
    """Calculate MD5 checksum to detect file changes."""
    if not os.path.exists(filepath):
        return ""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_price_history():
    """Load existing price fluctuation history."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_price_history(history_data):
    """Save price fluctuation history."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)


def get_existing_brand_prices(brand_name):
    """Read existing prices from CSV for comparison."""
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    prices = {}
    if os.path.exists(target_csv):
        try:
            with open(target_csv, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    model = (row.get("型号") or row.get("Model") or "").strip()
                    price = (
                        row.get("开机屏好")
                        or row.get("开机靓好")
                        or row.get("开机屏好(无ID)")
                        or ""
                    ).strip()
                    if model and price and price.isdigit():
                        prices[model] = int(price)
        except Exception:
            pass
    return prices


# ==================== Module 1: Image Downloader ====================
def fetch_poster_images(session):
    """Scrape and download quotation poster images to images/ directory."""
    print(f"[{datetime.now()}] Searching for poster images at {INDEX_URL}...")
    try:
        res = session.get(INDEX_URL, timeout=20)
        res.encoding = res.apparent_encoding or "utf-8"
        if res.status_code != 200:
            print(f"Warning: Failed to fetch index page (Status: {res.status_code})")
            return []
    except Exception as e:
        print(f"Network error while requesting index: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    img_tags = soup.find_all("img")
    updated_images = []

    for img in img_tags:
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("src")
            or ""
        )
        alt = img.get("alt") or img.get("title") or ""

        if not src or any(
            x in src.lower()
            for x in ["logo", "icon", "banner", "footer", "button"]
        ):
            continue

        if not src.startswith("http"):
            src = requests.compat.urljoin(BASE_URL, src)

        # Match brand name from URL or alt text
        brand_name = None
        for brand in KNOWN_BRANDS:
            if brand.lower() in (alt + src).lower():
                brand_name = brand
                break

        if not brand_name:
            clean_name = os.path.splitext(os.path.basename(src.split("?")[0]))[
                0
            ]
            if len(clean_name) < 2 or "index" in clean_name.lower():
                continue
            brand_name = clean_name

        save_filename = f"{brand_name}.jpg"
        save_path = os.path.join(IMAGE_DIR, save_filename)

        try:
            img_res = session.get(src, timeout=30)
            # Must be a valid image file (> 50KB to exclude small icons)
            if img_res.status_code == 200 and len(img_res.content) > 50 * 1024:
                new_md5 = hashlib.md5(img_res.content).hexdigest()
                old_md5 = get_file_md5(save_path)

                if new_md5 != old_md5:
                    with open(save_path, "wb") as f:
                        f.write(img_res.content)
                    print(
                        f"-> Downloaded updated poster: {save_filename} ({len(img_res.content) // 1024} KB)"
                    )
                    updated_images.append((brand_name, save_path))
                else:
                    print(f"-> Unchanged: {save_filename} matches local cache")
        except Exception as e:
            print(f"Failed to download image {src}: {e}")

    return updated_images


# ==================== Module 2: Long Image Slicing OCR ====================
def slice_and_ocr(image_path, slice_height=2000, overlap=100):
    """
    Slices ultra-tall images (e.g. 1080x30000 px) into smaller segments
    with an overlap margin to prevent out-of-memory errors and blurry text.
    """
    if ocr_engine is None:
        print(
            "RapidOCR not installed. Run: pip install rapidocr_onnxruntime"
        )
        return []

    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"Cannot open image {image_path}: {e}")
        return []

    width, height = img.size
    print(f"Processing OCR on: {os.path.basename(image_path)} ({width}x{height} px)...")

    all_lines = []
    y = 0

    while y < height:
        box_bottom = min(y + slice_height, height)
        slice_img = img.crop((0, y, width, box_bottom))

        result, _ = ocr_engine(slice_img)
        if result:
            for item in result:
                text = item[1].strip()
                if text:
                    all_lines.append(text)

        if box_bottom == height:
            break
        y += slice_height - overlap

    # Remove duplicates on slice boundaries
    deduped = []
    for line in all_lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    return deduped


# ==================== Module 3: Sync & Fluctuations ====================
def parse_and_update_csv(brand_name, raw_lines, history_data):
    """Parses text lines, compares old prices, and writes updated CSV data."""
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    old_prices = get_existing_brand_prices(brand_name)

    # Standard Chinese headers preserved for trade compatibility
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
    parsed_rows = []
    idx = 1
    price_change_count = 0

    for text in raw_lines:
        parts = re.split(r"[\s\t|,，/]+", text)
        digits = [p for p in parts if p.isdigit()]

        if len(parts) >= 3 and len(digits) >= 1:
            model = parts[0]
            if model in ["型号", "序号", "机型", "开机屏好", "Model"]:
                continue

            p_good = digits[0] if len(digits) > 0 else "-"
            p_bad = digits[1] if len(digits) > 1 else p_good
            p_no_pwr = digits[2] if len(digits) > 2 else p_bad
            p_junk = digits[3] if len(digits) > 3 else p_no_pwr
            remark = parts[-1] if not parts[-1].isdigit() else ""

            # Check and log price changes
            if model in old_prices and p_good.isdigit():
                curr_p = int(p_good)
                prev_p = old_prices[model]
                if curr_p != prev_p:
                    diff = curr_p - prev_p
                    key = f"{brand_name}_{model}"
                    history_data[key] = {
                        "brand": brand_name,
                        "model": model,
                        "old_price": prev_p,
                        "new_price": curr_p,
                        "diff": diff,
                        "update_time": datetime.now().strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    }
                    price_change_count += 1
                    trend = "UP +" if diff > 0 else "DOWN -"
                    print(
                        f"  [Price Change] {model}: {prev_p} -> {curr_p} ({trend}{abs(diff)})"
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
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(parsed_rows)
        print(
            f"Successfully updated {target_csv} ({len(parsed_rows)} items, {price_change_count} changed)"
        )


# ==================== Main Runner ====================
def main():
    print(f"=== Starting update_prices.py at {datetime.now()} ===")
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Download updated poster images
    updated_images = fetch_poster_images(session)

    # Fallback: scan all existing local images if no online changes were pulled
    local_images = [
        (os.path.splitext(f)[0], os.path.join(IMAGE_DIR, f))
        for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]

    target_images = updated_images if updated_images else local_images
    history_data = load_price_history()

    # 2. Run OCR and update CSVs
    for brand, img_path in target_images:
        try:
            lines = slice_and_ocr(img_path)
            if lines:
                parse_and_update_csv(brand, lines, history_data)
        except Exception as e:
            print(f"Error processing {brand} ({img_path}): {e}")

    # 3. Save all updated price fluctuation history
    save_price_history(history_data)
    print("=== Price update process finished successfully ===")


if __name__ == "__main__":
    main()
