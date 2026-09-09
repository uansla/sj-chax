# 📱 手机回收价格秒查工具（sj-chax）

一个基于 Python/Tkinter 的 Windows 手机回收价格查询工具。程序从 EXE 同级的 `data/` 目录读取 CSV，不把价格数据写死在 EXE 中，因此更新 CSV 后无需重新编译程序。

## ✨ 当前功能

- 🔍 输入型号、品牌、系列或价格信息即可实时模糊搜索。
- ✕ 搜索框提供一键清空按钮，旁边也提供“清空”按钮。
- 🔄 支持手动刷新 CSV 数据。
- 📂 支持直接打开 EXE 同级的 `data` 数据目录。
- 📊 支持不同 CSV 使用不同表头，并支持一个 CSV 内存在多段表格/表头。
- 📋 查询界面包含品牌、系列、序号、机型规格、网络型号、靓好、好屏、碎屏、坏配件、不开机、废板、统货、备注等字段。
- 🖥️ Windows 高 DPI 适配，使用 Tkinter，无第三方 GUI 框架。
- 📦 GitHub Actions 自动构建 Windows EXE，并将 `data/` 中全部 CSV 一起放入发布 ZIP。

## 📂 仓库结构

```text
sj-chax/
├── .github/
│   └── workflows/
│       ├── build_and_release.yml    # Windows EXE 自动构建与发布
│       └── daily_auto_sync.yml      # 每日自动抓取/OCR 同步
├── data/                            # 手机回收价格 CSV
├── images/                          # OCR/同步使用的图片
├── phone_search.py                  # Windows 桌面查询程序
├── auto_pipeline.py                 # 自动抓取、OCR、CSV 同步
├── ocr_update.py                    # 本地图片 OCR 更新工具
├── requirements.txt                 # 项目依赖
├── .gitignore
└── README.md
```

## 🚀 本地运行

### 1. 直接运行查询工具

查询程序只依赖 Python 标准库中的 Tkinter：

```bash
git clone https://github.com/uansla/sj-chax.git
cd sj-chax
python phone_search.py
```

Windows 如果已经安装 Python，也可以直接双击 `phone_search.py`。

### 2. 安装自动同步/OCR依赖

```bash
python -m pip install -r requirements.txt
```

## 📦 Windows EXE 自动打包

GitHub Actions 工作流：`.github/workflows/build_and_release.yml`。

触发方式：

1. 推送 `v*` 格式的 Git Tag，例如 `v1.2.0`。
2. 在 GitHub Actions 中手动运行，并填写版本号，例如 `v1.2.0`。

构建过程会先检查 `phone_search.py` 语法和 `data/` 是否存在 CSV，然后使用 PyInstaller 构建单文件 EXE。之后会创建：

```text
PhonePriceSearch_Windows.zip
└── 手机回收价格秒查工具.exe
└── 使用说明.txt
└── data/
    ├── *.csv
    └── ...
```

**注意：EXE 和 `data` 文件夹必须保持同级。** 程序启动后会自动读取 EXE 所在目录下的 `data/`。

因此以后只需要替换 `data/` 里的 CSV，就可以更新报价，不需要重新编译 EXE。

## 🤖 每日自动同步

`.github/workflows/daily_auto_sync.yml` 每天 UTC 00:30（北京时间 08:30）运行 `auto_pipeline.py`。

流水线会：

1. 从目标网站抓取图片。
2. 使用 RapidOCR 识别价格表。
3. 将识别结果写入 `data/`。
4. 将发生变化的 `data/` 和 `images/` 提交到 `main`。

为避免 OCR/网络异常导致数据被清空，当前程序在没有得到有效价格行时不会覆盖原 CSV。

GitHub Actions 需要仓库具有 `contents: write` 权限。工作流已经声明该权限；如果仓库设置限制了 Actions 写权限，请在仓库 Settings → Actions → General → Workflow permissions 中允许写入。

## 📋 CSV 数据兼容说明

查询程序不会要求所有 CSV 必须使用完全相同的表头。它会自动识别常见字段，例如：

- `品牌/系列`、`系列分类`、`系列` → 系列
- `机型与规格`、`机型及规格`、`型号` → 机型规格
- `网络制式型号`、`网络型号`、`网络制式` → 网络型号
- `开机靓好`、`靓好` → 靓好
- `开机好碎`、`开机好屏`、`好碎`、`好屏` → 好屏
- `开机碎屏`、`开机屏坏` → 碎屏
- `开机坏配件`、`开机压屏` → 坏配件
- `废板·整机`、`废板-整机`、`废板` → 废板
- `统货`、`开机无灯光` → 统货

界面统一显示为 **“好屏”**，旧数据中仍然存在的 `好碎` 字段也可以继续读取。

## ⚠️ 使用说明

回收价格数据仅供行情参考。实际成交价格以回收平台或回收商当日质检结果为准。

项目中的网络抓取/OCR 功能依赖目标网站结构；如果网站页面或图片格式发生变化，自动同步可能需要相应调整。
