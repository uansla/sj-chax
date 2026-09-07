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


def get_file_md5(filepath):
    if not os.path.exists(filepath):
        return ""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def crawl_and_download_images():
    print(f"[{datetime.now()}] Fetching price poster images from {INDEX_URL}...")
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        res = session.get(INDEX_URL, timeout=20)
        res.encoding = res.apparent_encoding or "utf-8"
        if res.status_code != 200:
            print(f"Failed to load index page, status code: {res.status_code}")
            return []
    except Exception as e:
        print(f"Network error: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    img_tags = soup.find_all("img")
    downloaded_images = []

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

        brand_name = None
        for brand in [
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
        ]:
            if brand.lower() in (alt + src).lower():
                brand_name = brand
                break

        if not brand_name:
            brand_name = os.path.splitext(os.path.basename(src.split("?")[0]))[
                0
            ]
            if len(brand_name) < 2 or "index" in brand_name.lower():
                continue

        save_filename = f"{brand_name}.jpg"
        save_path = os.path.join(IMAGE_DIR, save_filename)

        try:
            img_res = session.get(src, timeout=30)
            if img_res.status_code == 200 and len(img_res.content) > 50 * 1024:
                new_md5 = hashlib.md5(img_res.content).hexdigest()
                old_md5 = get_file_md5(save_path)

                if new_md5 != old_md5:
                    with open(save_path, "wb") as f:
                        f.write(img_res.content)
                    print(
                        f"Downloaded new poster: {save_filename} ({len(img_res.content)//1024} KB)"
                    )
                    downloaded_images.append((brand_name, save_path))
                else:
                    print(
                        f"No change detected for {save_filename}, skipping download"
                    )
        except Exception as e:
            print(f"Error downloading {src}: {e}")

    return downloaded_images


def slice_and_ocr_long_image(image_path, slice_height=2000, overlap=100):
    if ocr_engine is None:
        raise RuntimeError("RapidOCR engine not found. Run pip install rapidocr_onnxruntime")

    img = Image.open(image_path)
    width, height = img.size
    print(f"Running slice OCR on {os.path.basename(image_path)} ({width}x{height})...")

    all_ocr_lines = []
    y = 0

    while y < height:
        box_bottom = min(y + slice_height, height)
        slice_img = img.crop((0, y, width, box_bottom))

        result, _ = ocr_engine(slice_img)
        if result:
            for item in result:
                text = item[1].strip()
                if text:
                    all_ocr_lines.append(text)

        if box_bottom == height:
            break
        y += slice_height - overlap

    unique_lines = []
    for line in all_ocr_lines:
        if not unique_lines or line != unique_lines[-1]:
            unique_lines.append(line)

    return unique_lines


def parse_and_sync_prices(brand_name, ocr_lines):
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")

    old_prices = {}
    if os.path.exists(target_csv):
        try:
            with open(target_csv, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    m = (row.get("型号") or row.get("Model") or "").strip()
                    p = (
                        row.get("开机屏好")
                        or row.get("开机靓好")
                        or row.get("开机屏好(无ID)")
                        or ""
                    ).strip()
                    if m and p and p.isdigit():
                        old_prices[m] = int(p)
        except Exception:
            pass

    history_data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            history_data = {}

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

    for text in ocr_lines:
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
                        f"Price fluctuation: {model} {prev_price} -> {curr_price} (diff: {diff})"
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
        print(f"Updated CSV: {target_csv} ({len(parsed_rows)} models)")

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)


def run_pipeline():
    print(f"=== Starting auto update pipeline ({datetime.now()}) ===")
    updated_images = crawl_and_download_images()

    all_local_imgs = [
        (
            os.path.splitext(f)[0],
            os.path.join(IMAGE_DIR, f),
        )
        for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]

    target_process_list = updated_images if updated_images else all_local_imgs

    for brand, img_path in target_process_list:
        try:
            lines = slice_and_ocr_long_image(img_path)
            parse_and_sync_prices(brand, lines)
        except Exception as e:
            print(f"Error processing {brand}: {e}")

    print("=== Pipeline execution finished ===")


if __name__ == "__main__":
    run_pipeline()
