"""兼容旧脚本入口：报价已改为直接抓取网页表格，不再做图片 OCR。"""

from auto_pipeline import run_pipeline


if __name__ == "__main__":
    print("旧版图片 OCR 已停用，开始直接同步官网网页报价。")
    print(run_pipeline(print))
