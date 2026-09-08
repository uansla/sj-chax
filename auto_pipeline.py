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

# 严格 10 列定义
CSV_HEADERS = ["系列", "序号", "型号", "开机靓好", "开机好碎", "开机碎屏", "开机压屏", "不开机", "废板-整机", "备注"]

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}

def get_file_md5(filepath):
    if not os.path.exists(filepath): return ""
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
        res.encoding = res.apparent_encoding
        if res.status_code != 200: return []
    except Exception as e:
        print(f"网络错误: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    img_tags = soup.find_all("img")
    downloaded_images = []

    for img in img_tags:
        src = img.get("data-src") or img.get("data-original") or img.get("src") or ""
        alt = img.get("alt") or img.get("title") or ""
        if not src or any(x in src.lower() for x in ["logo", "icon", "banner"]): continue
        if not src.startswith("http"): src = requests.compat.urljoin(BASE_URL, src)

        # 匹配品牌名作为文件名
        brand_name = "Other"
        known_brands = ["Apple", "Huawei", "Honor", "OPPO", "VIVO", "Xiaomi", "Redmi", "Samsung", "OnePlus", "Realme", "Meizu"]
        for b in known_brands:
            if b.lower() in (alt + src).lower():
                brand_name = b
                break
        
        save_path = os.path.join(IMAGE_DIR, f"{brand_name}.jpg")
        try:
            img_res = session.get(src, timeout=30)
            if img_res.status_code == 200:
                new_md5 = hashlib.md5(img_res.content).hexdigest()
                if new_md5 != get_file_md5(save_path):
                    with open(save_path, "wb") as f: f.write(img_res.content)
                    downloaded_images.append((brand_name, save_path))
                    print(f"下载新海报: {brand_name}.jpg")
        except: pass
    return downloaded_images

def slice_and_ocr_long_image(image_path, slice_height=2000):
    img = Image.open(image_path)
    width, height = img.size
    all_ocr_lines = []
    y = 0
    while y < height:
        box_bottom = min(y + slice_height, height)
        slice_img = img.crop((0, y, width, box_bottom))
        result, _ = ocr_engine(slice_img)
        if result:
            for item in result: all_ocr_lines.append(item[1].strip())
        y += slice_height - 100 # 重叠100像素防止断行
    return all_ocr_lines

def parse_and_sync_prices(brand_name, ocr_lines):
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")
    parsed_rows = []
    idx = 1
    
    # 历史记录加载
    history_data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: history_data = json.load(f)
        except: pass

    for text in ocr_lines:
        # 正则提取：第一段通常是型号，后面跟着一串数字价格
        parts = re.split(r"[\s\t|,，/]+", text)
        digits = [p for p in parts if re.match(r"^\d+$", p)]
        
        if len(parts) >= 2 and len(digits) >= 1:
            model = parts[0]
            if model in ["型号", "序号", "机型", "开机靓好"]: continue
            
            # 自动补全 6 个价格位：靓好, 好碎, 碎屏, 压屏, 不开机, 废板
            # 如果 OCR 只识别到 4 个数字，则后面两个自动重复最后一个数字
            prices = []
            for i in range(6):
                if i < len(digits):
                    prices.append(digits[i])
                else:
                    prices.append(digits[-1] if digits else "0")
            
            remark = parts[-1] if not parts[-1].isdigit() else ""
            
            parsed_rows.append({
                "系列": brand_name,
                "序号": str(idx),
                "型号": model,
                "开机靓好": prices[0],
                "开机好碎": prices[1],
                "开机碎屏": prices[2],
                "开机压屏": prices[3],
                "不开机": prices[4],
                "废板-整机": prices[5],
                "备注": remark
            })
            idx += 1

    if parsed_rows:
        with open(target_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(parsed_rows)
        print(f"CSV同步完成: {brand_name}.csv, 共 {len(parsed_rows)} 行")

def run_pipeline():
    updated = crawl_and_download_images()
    # 如果没下到新的，就扫描本地目录
    process_list = updated if updated else [(os.path.splitext(f)[0], os.path.join(IMAGE_DIR, f)) for f in os.listdir(IMAGE_DIR) if f.endswith(".jpg")]
    
    for brand, img_path in process_list:
        try:
            lines = slice_and_ocr_long_image(img_path)
            parse_and_sync_prices(brand, lines)
        except Exception as e:
            print(f"处理 {brand} 失败: {e}")

if __name__ == "__main__":
    run_pipeline()
