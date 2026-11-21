"""从数码回收网报价历史页抓取各品牌最近七份报价表。"""

from __future__ import annotations

import csv
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.smhsw.com"
INDEX_URL = f"{BASE_URL}/home/quotation/more.html"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Referer": INDEX_URL,
}
DATE_RE = re.compile(r"(?P<y>20\d{2})[年/-](?P<m>\d{1,2})[月/-](?P<d>\d{1,2})")
MODEL_MARKERS = ("型号", "机型", "商品型号", "品名/型号")
HISTORY_START = date(2026, 10, 1)


def create_session(proxies: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(HEADERS)
    if proxies:
        session.proxies.update(proxies)
    return session


def parse_date(value: str) -> date | None:
    match = DATE_RE.search(value or "")
    if not match:
        return None
    try:
        return date(int(match["y"]), int(match["m"]), int(match["d"]))
    except ValueError:
        return None


def fetch_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, timeout=(10, 30))
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def find_brand_pages(soup: BeautifulSoup) -> list[tuple[str, str]]:
    found = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, anchor["href"])
        if "/home/quotation/more/" not in urlparse(href).path:
            continue
        match = re.search(r"/p_id/(\d+)/cat_id/(\d+)", urlparse(href).path)
        # 用户指定只抓“二手手机”下的品牌；其品牌入口均为 p_id=1 且 cat_id>0。
        if not match or match.group(1) != "1" or match.group(2) == "0":
            continue
        brand = " ".join(anchor.get_text(" ", strip=True).split())
        if not brand or brand in {"更多", "下一页", "上一页"}:
            continue
        key = (brand, href.rstrip("/"))
        if key not in seen:
            seen.add(key)
            found.append((brand, href))
    return found


def find_recent_articles(soup: BeautifulSoup, start_date: date = HISTORY_START) -> list[tuple[date, str]]:
    by_url = {}
    today = date.today()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, anchor["href"])
        path = urlparse(href).path
        if "/home/quotation/index/" not in path:
            continue
        label = " ".join(anchor.get_text(" ", strip=True).split())
        article_date = parse_date(href) or parse_date(label)
        if article_date and start_date <= article_date <= today:
            by_url[href] = article_date
    return sorted(((d, u) for u, d in by_url.items()), reverse=True)


def find_article_pages(session: requests.Session, brand_url: str) -> list[tuple[date, str]]:
    """读取品牌报价列表及其分页，直到历史日期早于采集起点。"""
    base_path = urlparse(brand_url).path.rstrip("/")
    pending = [brand_url]
    visited = set()
    articles = {}
    while pending and len(visited) < 12:
        listing_url = pending.pop(0)
        if listing_url in visited:
            continue
        visited.add(listing_url)
        soup = fetch_soup(session, listing_url)
        page_articles = find_recent_articles(soup, date.min)
        for quote_date, article_url in page_articles:
            if quote_date >= HISTORY_START:
                articles[article_url] = quote_date
        page_dates = [d for d, _ in page_articles]
        if page_dates and min(page_dates) < HISTORY_START:
            continue
        for anchor in soup.find_all("a", href=True):
            href = urljoin(BASE_URL, anchor["href"])
            path = urlparse(href).path.rstrip("/")
            if path.startswith(base_path) and href not in visited and href not in pending and href != brand_url:
                # 限制在本品牌列表的分页链接，避免递归到其他品牌/详情页。
                if "/home/quotation/index/" not in path:
                    pending.append(href)
    return sorted(((d, u) for u, d in articles.items()), reverse=True)


def parse_quote_table(soup: BeautifulSoup) -> tuple[list[str], list[list[str]]]:
    """选择包含型号表头的最大表格，跳过导航/页脚中的其他表格。"""
    candidates = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            values = [" ".join(cell.stripped_strings).strip() for cell in cells]
            if any(values):
                rows.append(values)
        for index, row in enumerate(rows):
            if any(marker in cell.replace(" ", "") for cell in row for marker in MODEL_MARKERS):
                header = row
                body = [r for r in rows[index + 1:] if len(r) >= 2]
                candidates.append((len(body), header, body))
                break
    if candidates:
        _, header, rows = max(candidates, key=lambda item: item[0])
        return header, rows

    # 有些版本将报价表直接渲染为 div；保留对纯文本分隔表格的兼容。
    text = soup.get_text("\n", strip=True)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    header_index = next((i for i, line in enumerate(lines) if "型号" in line and re.search(r"开机|靓机|充新|靓好", line)), None)
    if header_index is None:
        return [], []
    split = lambda line: [x.strip() for x in re.split(r"\s*[|｜\t]\s*", line.strip(" |｜")) if x.strip()]
    header = split(lines[header_index])
    body = []
    for line in lines[header_index + 1:]:
        row = split(line)
        if len(row) >= 2:
            body.append(row)
    return header, body


def clean_header(value: str, index: int) -> str:
    value = re.sub(r"\s+", "", value).strip("*|｜")
    return value or f"报价项{index}"


def valid_quote_rows(header: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    model_index = next((i for i, value in enumerate(header) if any(marker in value.replace(" ", "") for marker in MODEL_MARKERS)), None)
    if model_index is None:
        return []
    headers = [clean_header(v, i + 1) for i, v in enumerate(header)]
    output = []
    for row in rows:
        if model_index >= len(row):
            continue
        model = re.sub(r"\s+", " ", row[model_index]).strip()
        if not model or model in MODEL_MARKERS or set(model) <= {"-", "—", "*", "="}:
            continue
        record = {"型号": model}
        for i, value in enumerate(row[:len(headers)]):
            if i == model_index:
                continue
            label = headers[i]
            if label in ("型号", "序号"):
                continue
            record[label] = value.strip()
        if any(re.search(r"\d", value) for key, value in record.items() if key != "型号"):
            output.append(record)
    return output


def write_snapshot(brand: str, quote_date: date, rows: list[dict[str, str]], source: str, data_dir: Path | str | None = None) -> Path:
    # 每份报价保留原网站的不同报价档位，便于后续扩展展示字段。
    all_fields = []
    for row in rows:
        for field in row:
            if field not in all_fields:
                all_fields.append(field)
    headers = ["报价日期", "系列", "型号"] + [x for x in all_fields if x != "型号"] + ["来源"]
    safe_brand = re.sub(r'[\\/:*?"<>|]+', "_", brand).strip() or "未知品牌"
    output_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    brand_dir = output_dir / safe_brand
    target = brand_dir / f"{quote_date.isoformat()}_{safe_brand}.csv"
    brand_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=brand_dir, delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({"报价日期": quote_date.isoformat(), "系列": brand, "来源": source, **row})
        temp_path = Path(tmp.name)
    temp_path.replace(target)
    return target


def prune_old_snapshots(start_date: date = HISTORY_START) -> int:
    files = list(DATA_DIR.rglob("????-??-??_*.csv"))
    removed = 0
    for path in files:
        file_date = parse_date(path.name)
        if file_date and file_date < start_date:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def run_pipeline(progress=None, data_dir: Path | str | None = None, proxies: dict[str, str] | None = None) -> dict[str, int]:
    """下载二手手机分类下所有品牌自 2026-10-01 起的报价。"""
    report = {"brands": 0, "snapshots": 0, "rows": 0, "errors": 0}
    output_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    session = create_session(proxies)
    try:
        index = fetch_soup(session, INDEX_URL)
    finally:
        session.close()
    brands = find_brand_pages(index)
    if not brands:
        raise RuntimeError("报价总览页没有找到品牌报价入口，网站页面可能已调整。")
    for brand, _ in brands:
        folder = re.sub(r'[\\/:*?"<>|]+', "_", brand).strip() or "未知品牌"
        (output_dir / folder).mkdir(parents=True, exist_ok=True)

    def process_brand(brand: str, brand_url: str) -> dict[str, int]:
        result = {"brands": 1, "snapshots": 0, "rows": 0, "errors": 0}
        if progress:
            progress(f"正在更新 {brand}…")
        worker_session = create_session(proxies)
        try:
            articles = find_article_pages(worker_session, brand_url)
            safe_brand = re.sub(r'[\\/:*?"<>|]+', "_", brand).strip() or "未知品牌"
            for quote_date, article_url in articles:
                # 已有报价按品牌和日期保留，只抓本地缺少的快照，避免重复下载或覆盖用户文件。
                target = output_dir / safe_brand / f"{quote_date.isoformat()}_{safe_brand}.csv"
                if target.is_file():
                    continue
                try:
                    page = fetch_soup(worker_session, article_url)
                    header, raw_rows = parse_quote_table(page)
                    rows = valid_quote_rows(header, raw_rows)
                    if not rows:
                        result["errors"] += 1
                        continue
                    write_snapshot(brand, quote_date, rows, article_url, output_dir)
                    result["snapshots"] += 1
                    result["rows"] += len(rows)
                    time.sleep(0.05)
                except (requests.RequestException, ValueError, OSError):
                    result["errors"] += 1
        except (requests.RequestException, ValueError, OSError):
            result["errors"] += 1
        finally:
            worker_session.close()
        return result

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(process_brand, brand, url) for brand, url in brands]
        for future in as_completed(futures):
            result = future.result()
            for key in report:
                report[key] += result[key]

    # 保留用户自行放入 data/ 的 CSV，不清理本地文件。
    return report


if __name__ == "__main__":
    started = datetime.now()
    result = run_pipeline(print)
    print(f"完成：{result}，耗时 {datetime.now() - started}")
