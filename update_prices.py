import csv
import json
import os
import re
import sys
from datetime import datetime
from bs4 import BeautifulSoup
import requests

# 目标网址
BASE_URL = "https://www.smhsw.com"
INDEX_URL = "https://www.smhsw.com/index/index/index.html"

# 请求头伪装（模拟移动端/微信浏览器，与数码回收网适配更好）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
        "MicroMessenger/8.0.38 NetType/WIFI Language/zh_CN"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    ),
    "Referer": BASE_URL,
}

# 基础路径定义
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def get_session():
    """创建保持会话的 requests session"""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def save_brand_csv(brand_name, rows, headers=None):
    """保存单一品牌/分类的数据到 data/ 文件夹下"""
    if not rows:
        return

    csv_path = os.path.join(DATA_DIR, f"{brand_name}.csv")

    # 标准表头
    if not headers:
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

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            # 过滤并写入标准字段
            filtered_row = {k: r.get(k, "") for k in headers}
            writer.writerow(filtered_row)

    print(f"[{datetime.now()}] ✅ 已保存: {csv_path} (共 {len(rows)} 条)")


def fetch_and_parse(session):
    """
    抓取数码回收网首页及各分类价格数据
    网站通常有两种组织方式：
    1. 页面直接内嵌 HTML 表格或 JSON 接口
    2. 分类链接到各子页面（如 oppo/vivo/apple 等）
    """
    print(f"正在请求首页: {INDEX_URL} ...")
    try:
        resp = session.get(INDEX_URL, timeout=20)
        resp.encoding = resp.apparent_encoding or "utf-8"
        if resp.status_code != 200:
            print(f"请求失败，状态码: {resp.status_code}")
            return False
    except Exception as e:
        print(f"网络异常: {e}")
        return False

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. 检测是否有可直接提取的表格 <table>
    tables = soup.find_all("table")
    if tables:
        print(f"页面共找到 {len(tables)} 个价格数据表，开始解析...")
        # 解析页面中的所有表格
        for idx, table in enumerate(tables):
            # 获取表格标题或品牌
            caption = table.find("caption") or table.find_previous(
                ["h1", "h2", "h3", "div"]
            )
            brand = caption.get_text(strip=True) if caption else f"分类_{idx+1}"
            brand = re.sub(r'[\\/:*?"<>|]', "", brand)  # 清理文件名非法字符

            rows_data = []
            tr_list = table.find_all("tr")
            for tr in tr_list:
                tds = [
                    td.get_text(strip=True) for td in tr.find_all(["td", "th"])
                ]
                if not tds or len(tds) < 3:
                    continue

                # 排除表头行
                if "型号" in tds or "开机屏好" in tds:
                    continue

                row = {
                    "系列": brand,
                    "序号": tds[0] if len(tds) > 0 else "",
                    "型号": tds[1] if len(tds) > 1 else "",
                    "开机屏好": tds[2] if len(tds) > 2 else "",
                    "开机屏坏": tds[3] if len(tds) > 3 else "",
                    "不开机": tds[4] if len(tds) > 4 else "",
                    "废板-整机": tds[5] if len(tds) > 5 else "",
                    "备注": tds[6] if len(tds) > 6 else "",
                }
                rows_data.append(row)

            if rows_data:
                save_brand_csv(brand, rows_data)

    # 2. 检测是否有分类链接或 API 接口（根据具体页面路由爬取子页面）
    # 例如包含各个品牌板块的超链接
    brand_links = soup.select("a[href*='index'], a[href*='price']")
    for a in brand_links:
        link = a.get("href")
        brand_title = a.get_text(strip=True)
        if not link or len(brand_title) < 2:
            continue
        if not link.startswith("http"):
            link = requests.compat.urljoin(BASE_URL, link)
        # 针对每个品牌的详情页继续解析表格（结构同上）

    print(f"数据抓取更新完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return True


if __name__ == "__main__":
    s = get_session()
    fetch_and_parse(s)
