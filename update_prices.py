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

# 尝试载入高效离线 OCR 引擎
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
    """计算本地已有文件 MD5，避免重复重复识别未变更的图片"""
    if not os.path.exists(filepath):
        return ""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# ==================== 模块 1：长图爬取器 ====================
def crawl_and_download_images():
    """扫描数码回收网，把最新的超长报价海报图直接保存到 images/ 目录"""
    print(f"[{datetime.now()}] 🌐 正在检索数码回收网海报图片...")
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        res = session.get(INDEX_URL, timeout=20)
        res.encoding = res.apparent_encoding or "utf-8"
        if res.status_code != 200:
            print(f"❌ 首页请求失败，状态码: {res.status_code}")
            return []
    except Exception as e:
        print(f"❌ 网络异常: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    # 查找所有图片标签 (含懒加载 data-src / data-original)
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

        # 尝试推导品牌名称 (如: OPPO, Vivo, 苹果, 华为)
        brand_name = None
        for brand in [
            "苹果",
            "Apple",
            "华为",
            "荣耀",
            "OPPO",
            "VIVO",
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
            "HTC",
            "TCL",
            "美图",
            "糖果",
            "海信",
            "移动",
            "奇酷",
            "功能机",
        ]:
            if brand.lower() in (alt + src).lower():
                brand_name = brand
                break

        if not brand_name:
            # 根据文件名作为后备名称
            brand_name = os.path.splitext(os.path.basename(src.split("?")[0]))[
                0
            ]
            if len(brand_name) < 2 or "index" in brand_name.lower():
                continue

        save_filename = f"{brand_name}.jpg"
        save_path = os.path.join(IMAGE_DIR, save_filename)

        # 下载图片流并比对 MD5
        try:
            img_res = session.get(src, timeout=30)
            if img_res.status_code == 200 and len(img_res.content) > 50 * 1024:
                # 必须大于 50KB，排除小图标
                new_md5 = hashlib.md5(img_res.content).hexdigest()
                old_md5 = get_file_md5(save_path)

                if new_md5 != old_md5:
                    with open(save_path, "wb") as f:
                        f.write(img_res.content)
                    print(
                        f"📥 [检测到更新] 下载长图: {save_filename} ({len(img_res.content)//1024} KB)"
                    )
                    downloaded_images.append((brand_name, save_path))
                else:
                    print(
                        f"⏩ [无变动] {save_filename} 图片内容与本地一致，跳过下载与识别"
                    )
        except Exception as e:
            print(f"⚠️ 下载图片 {src} 异常: {e}")

    return downloaded_images


# ==================== 模块 2：超长海报切片 OCR 引擎 ====================
def slice_and_ocr_long_image(image_path, slice_height=2000, overlap=100):
    """
    智能切片算法：针对长达数万像素的长图，用滑动窗口切成若干个小图送进 OCR，
    避免超长图导致显存/内存撑爆、或者长宽比过大识别模糊的问题。
    """
    if ocr_engine is None:
        raise RuntimeError("未检测到 RapidOCR 引擎，请执行 pip install rapidocr_onnxruntime")

    img = Image.open(image_path)
    width, height = img.size
    print(f"📸 正在对长图 [{os.path.basename(image_path)}] 执行分块识别 (尺寸: {width}x{height}) ...")

    all_ocr_lines = []
    y = 0

    while y < height:
        box_bottom = min(y + slice_height, height)
        # 截取局部块
        slice_img = img.crop((0, y, width, box_bottom))

        # 临时存为内存数组进行 OCR
        result, _ = ocr_engine(slice_img)
        if result:
            for item in result:
                text = item[1].strip()
                if text:
                    all_ocr_lines.append(text)

        if box_bottom == height:
            break
        y += slice_height - overlap

    # 去除切片重叠边界处的重复文本行
    unique_lines = []
    for line in all_ocr_lines:
        if not unique_lines or line != unique_lines[-1]:
            unique_lines.append(line)

    return unique_lines


# ==================== 模块 3：数据解析与价格变动归档 ====================
def parse_and_sync_prices(brand_name, ocr_lines):
    """解析 OCR 文本行，对比旧价格，更新 CSV 并记录涨跌到 price_history.json"""
    target_csv = os.path.join(DATA_DIR, f"{brand_name}.csv")

    # 读取旧价格用于对比变动
    old_prices = {}
    if os.path.exists(target_csv):
        try:
            with open(target_csv, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    m = (row.get("型号") or "").strip()
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

        # 一行中既包含机型又包含多个价格
        if len(parts) >= 3 and len(digits) >= 1:
            model = parts[0]
            if model in ["型号", "序号", "机型", "开机屏好"]:
                continue

            p_good = digits[0] if len(digits) > 0 else "-"
            p_bad = digits[1] if len(digits) > 1 else p_good
            p_no_pwr = digits[2] if len(digits) > 2 else p_bad
            p_junk = digits[3] if len(digits) > 3 else p_no_pwr
            remark = parts[-1] if not parts[-1].isdigit() else ""

            # 对比价格变动并打标
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
                    flag = "🔴 涨" if diff > 0 else "🟢 跌"
                    print(
                        f"  🔥 价格波动: {model} {prev_price} -> {curr_price} ({flag} {abs(diff)})"
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
        # 覆写 CSV 表格
        with open(target_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(parsed_rows)
        print(f"✅ [{brand_name}.csv] 表格已同步更新 (共写入 {len(parsed_rows)} 条数据)")

        # 同步更新 price_history.json
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)


# ==================== 主入口 ====================
def run_pipeline():
    print(f"=== 🚀 开始执行数码回收网每日自动同步流水线 ===")

    # 1. 抓取有更新的海报长图
    updated_images = crawl_and_download_images()

    # 如果有本地遗留未识别的图片也一并纳入
    all_local_imgs = [
        (
            os.path.splitext(f)[0],
            os.path.join(IMAGE_DIR, f),
        )
        for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".jpg", ".png", ".jpeg"))
    ]

    target_process_list = updated_images if updated_images else all_local_imgs

    # 2. 依次切片识别并更新对应 CSV
    for brand, img_path in target_process_list:
        try:
            lines = slice_and_ocr_long_image(img_path)
            parse_and_sync_prices(brand, lines)
        except Exception as e:
            print(f"❌ 识别/处理 {brand} 时出错: {e}")

    print(f"=== 🎉 流水线执行完毕！最新数据均已落盘到 data/ 目录 ===")


if __name__ == "__main__":
    run_pipeline()
