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

from series_classifier import infer_series

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
CATEGORY_PRODUCT_IDS = {"二手手机": 1, "手机内配": 2, "杂货铺": 3, "数码相机回收报价": 999999999, "电脑回收": 2147483647, "二手平板": 4, "家电回收": 5}


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


def find_brand_pages(soup: BeautifulSoup, product_id: int = 1) -> list[tuple[str, str]]:
    found = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, anchor["href"])
        if "/home/quotation/more/" not in urlparse(href).path:
            continue
        match = re.search(r"/p_id/(\\d+)/cat_id/(\\d+)", urlparse(href).path)
        if not match or match.group(1) != str(product_id) or match.group(2) == "0":
            continue
        brand = " ".join(anchor.get_text(" ", strip=True).split())
        if not brand or brand in {"更多", "下一页", "上一页"}:
            continue
        key = href.rstrip("/")
        if key not in seen:
            seen.add(key)
            found.append((brand, href))
    return found


def fetch_category_brands(session: requests.Session, product_id: int) -> list[tuple[str, str]]:
    index_url = INDEX_URL if product_id == 1 else f"{BASE_URL}/home/quotation/more/p_id/{product_id}/cat_id/0"
    return find_brand_pages(fetch_soup(session, index_url), product_id)

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


def find_article_pages(session: requests.Session, brand_url: str,
                       selected_dates: list[str] | None = None) -> list[tuple[date, str]]:
    """Return explicitly selected dates, or discover the current category's available articles."""
    base_path = urlparse(brand_url).path.rstrip("/")
    expected = re.search(r"/p_id/([0-9]+)/cat_id/([0-9]+)", base_path)
    if selected_dates is not None:
        if not expected:
            return []
        product_id, category_id = expected.groups()
        selected = []
        for value in selected_dates:
            quote_date = parse_date(value)
            if quote_date:
                url = (f"{BASE_URL}/home/quotation/index/p_id/{product_id}/cat_id/"
                       f"{category_id}/date/{quote_date.isoformat()}.html")
                selected.append((quote_date, url))
        return selected
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
        if expected:
            expected_category = expected.groups()
            page_articles = [
                (quote_date, article_url) for quote_date, article_url in page_articles
                if (match := re.search(r"/p_id/([0-9]+)/cat_id/([0-9]+)", urlparse(article_url).path))
                and match.groups() == expected_category
            ]
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
                if "/home/quotation/index/" not in path:
                    pending.append(href)
    return sorted(((quote_date, article_url) for article_url, quote_date in articles.items()), reverse=True)

def parse_quote_tables(soup: BeautifulSoup) -> list[tuple[list[str], list[list[str]]]]:
    """Return every model/pricing table, including smaller sub-series tables."""
    candidates = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            values = [" ".join(cell.stripped_strings).strip() for cell in cells]
            if any(values):
                rows.append(values)
        index = 0
        while index < len(rows):
            row = rows[index]
            if not any(marker in cell.replace(" ", "") for cell in row for marker in MODEL_MARKERS):
                index += 1
                continue
            header = row
            body = []
            index += 1
            while index < len(rows):
                next_row = rows[index]
                if any(marker in cell.replace(" ", "") for cell in next_row for marker in MODEL_MARKERS):
                    break
                if len(next_row) >= 2:
                    body.append(next_row)
                index += 1
            if body:
                candidates.append((header, body))
    if candidates:
        return candidates

    # Some site versions render the quote as text instead of a table.
    text = soup.get_text("\n", strip=True)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    header_index = next((i for i, line in enumerate(lines)
                         if "型号" in line and re.search(r"开机|靓机|充新|靓好", line)), None)
    if header_index is None:
        return []
    split = lambda line: [x.strip() for x in re.split(r"\s*[|｜\t]\s*", line.strip(" |｜")) if x.strip()]
    header = split(lines[header_index])
    body = []
    for line in lines[header_index + 1:]:
        row = split(line)
        if len(row) >= 2:
            body.append(row)
    return [(header, body)]


def parse_quote_table(soup: BeautifulSoup) -> tuple[list[str], list[list[str]]]:
    """Compatibility helper for callers expecting one table."""
    tables = parse_quote_tables(soup)
    if not tables:
        return [], []
    header = tables[0][0]
    rows = [row for section_header, section_rows in tables if section_header == header for row in section_rows]
    return header, rows


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


def normalize_name(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value.casefold(), flags=re.UNICODE)


def existing_snapshot(output_dir: Path, brand: str, quote_date: date) -> Path | None:
    date_prefix = quote_date.isoformat()
    wanted = normalize_name(brand)
    for path in output_dir.rglob("*.csv"):
        if not path.name.startswith(date_prefix):
            continue
        filename_brand = normalize_name(path.stem[len(date_prefix):].lstrip("_ -"))
        parent_brand = normalize_name(path.parent.name) if path.parent != output_dir else ""
        if filename_brand == wanted or parent_brand == wanted:
            return path
    return None


def write_snapshot(brand: str, quote_date: date, rows: list[dict[str, str]], source: str,
                   data_dir: Path | str | None = None,
                   category: str = "二手手机") -> tuple[Path, int]:
    all_fields = []
    for row in rows:
        for field in row:
            if field not in all_fields:
                all_fields.append(field)
    headers = ["报价日期", "分类", "系列", "型号"] + [
        field for field in all_fields if field not in {"报价日期", "分类", "系列", "型号"}
    ] + ["来源"]
    safe_brand = re.sub(r'[\\\\/:*?"<>|]+', "_", brand).strip() or "未知品牌"
    safe_category = re.sub(r'[\\\\/:*?"<>|]+', "_", category).strip() or "其他分类"
    output_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    category_dir = output_dir if category == "二手手机" else output_dir / safe_category
    brand_dir = category_dir / safe_brand
    target = existing_snapshot(category_dir, brand, quote_date) or (
        brand_dir / f"{quote_date.isoformat()}_{safe_brand}.csv"
    )
    brand_dir.mkdir(parents=True, exist_ok=True)
    existing_rows = []
    existing_headers = []
    model_header = "型号"
    if target.is_file():
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                with target.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle)
                    existing_headers = reader.fieldnames or []
                    model_header = next((name for name in existing_headers
                                         if any(marker in name.replace(" ", "") for marker in MODEL_MARKERS)), "")
                    existing_rows = list(reader)
                break
            except (UnicodeError, csv.Error, OSError):
                existing_rows, existing_headers = [], []
        if not model_header:
            target = brand_dir / f"{quote_date.isoformat()}_{safe_brand}_补充.csv"
            existing_rows, existing_headers, model_header = [], [], "型号"
    source_match = re.search(r"/p_id/([0-9]+)/cat_id/([0-9]+)", urlparse(source).path)
    if source_match:
        expected_category = source_match.groups()
        existing_rows = [
            row for row in existing_rows
            if not (old_source := row.get("来源", ""))
            or not (old_category := re.search(r"/p_id/([0-9]+)/cat_id/([0-9]+)", urlparse(old_source).path))
            or old_category.groups() == expected_category
        ]
    present = {normalize_name(row.get(model_header, "")) for row in existing_rows}
    merged = list(existing_rows)
    added = 0
    for row in rows:
        model_key = normalize_name(row.get("型号", ""))
        if not model_key or model_key in present:
            continue
        merged.append({"报价日期": quote_date.isoformat(), "分类": category,
                       "系列": row.get("系列") or infer_series(brand, row.get("型号", "")),
                       "来源": source, **row})
        present.add(model_key)
        added += 1
    fieldnames = list(dict.fromkeys(existing_headers + headers))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=target.parent, delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)
        temp_path = Path(tmp.name)
    temp_path.replace(target)
    return target, added

def prune_old_snapshots(start_date: date = HISTORY_START) -> int:
    files = list(DATA_DIR.rglob("????-??-??_*.csv"))
    removed = 0
    for path in files:
        file_date = parse_date(path.name)
        if file_date and file_date < start_date:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def run_pipeline(progress=None, data_dir: Path | str | None = None,
                 proxies: dict[str, str] | None = None,
                 categories: list[str] | None = None,
                 selected_dates: list[str] | None = None) -> dict[str, int]:
    """Update only requested categories and the exact manually selected dates."""
    report = {"categories": 0, "brands": 0, "snapshots": 0, "rows": 0,
              "errors": 0, "empty_pages": 0, "added_models": 0}
    output_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    if categories is None:
        requested_categories = ["二手手机"]
    else:
        requested_categories = list(dict.fromkeys(categories))
    if not requested_categories or selected_dates == []:
        return report
    unknown = [name for name in requested_categories if name not in CATEGORY_PRODUCT_IDS]
    if unknown:
        raise ValueError(f"不支持的报价分类：{', '.join(unknown)}")

    session = create_session(proxies)
    category_brands = {}
    try:
        for category in requested_categories:
            category_brands[category] = fetch_category_brands(
                session, CATEGORY_PRODUCT_IDS[category]
            )
    finally:
        session.close()
    if not any(category_brands.values()):
        raise RuntimeError("所选分类没有找到品牌入口，网站页面可能已调整。")

    def process_brand(category: str, brand: str, brand_url: str) -> dict[str, int]:
        result = {"categories": 0, "brands": 1, "snapshots": 0, "rows": 0,
                  "errors": 0, "empty_pages": 0, "added_models": 0}
        if progress:
            progress(f"正在更新 {category} / {brand}…")
        worker_session = create_session(proxies)
        try:
            articles = find_article_pages(worker_session, brand_url, selected_dates)
            safe_category = re.sub(r'[\\/:*?"<>|]+', "_", category).strip() or "其他分类"
            category_dir = output_dir if category == "二手手机" else output_dir / safe_category
            for quote_date, article_url in articles:
                if selected_dates is None and existing_snapshot(category_dir, brand, quote_date):
                    continue
                try:
                    page = fetch_soup(worker_session, article_url)
                    rows = []
                    for header, raw_rows in parse_quote_tables(page):
                        rows.extend(valid_quote_rows(header, raw_rows))
                    for row in rows:
                        row["系列"] = infer_series(brand, row.get("型号", ""))
                    if not rows:
                        result["empty_pages"] += 1
                        continue
                    _path, added = write_snapshot(
                        brand, quote_date, rows, article_url, output_dir, category
                    )
                    result["snapshots"] += 1
                    result["rows"] += len(rows)
                    result["added_models"] += added
                    time.sleep(0.05)
                except (requests.RequestException, ValueError, OSError) as exc:
                    result["errors"] += 1
                    print(f"报价抓取失败：{category}/{brand} {quote_date} {article_url} [{type(exc).__name__}: {exc}]")
        except (requests.RequestException, ValueError, OSError) as exc:
            result["errors"] += 1
            print(f"品牌列表读取失败：{category}/{brand} [{type(exc).__name__}: {exc}]")
        finally:
            worker_session.close()
        return result

    jobs = []
    for category, brands in category_brands.items():
        report["categories"] += 1
        safe_category = re.sub(r'[\\/:*?"<>|]+', "_", category).strip() or "其他分类"
        category_dir = output_dir if category == "二手手机" else output_dir / safe_category
        for brand, url in brands:
            safe_brand = re.sub(r'[\\/:*?"<>|]+', "_", brand).strip() or "未知品牌"
            (category_dir / safe_brand).mkdir(parents=True, exist_ok=True)
            jobs.append((category, brand, url))

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(process_brand, category, brand, url)
                   for category, brand, url in jobs]
        for future in as_completed(futures):
            result = future.result()
            for key in report:
                report[key] += result[key]

    return report

if __name__ == "__main__":
    started = datetime.now()
    result = run_pipeline(print)
    print(f"完成：{result}，耗时 {datetime.now() - started}")
