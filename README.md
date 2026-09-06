# 📱 手机与数码设备回收价格自动同步与秒查工具 (sj-chax)

[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Auto%20Sync-orange.svg)](#-自动化同步流程)

一个面向数码回收从业者、二手商贩与消费者的**自动化回收报价追踪与本地高速检索工具**。

本项目通过云端定时监控抓取「数码回收网」最新价格变动，自动格式化存储为结构化 CSV 表格，并配合本地轻量级桌面检索工具，实现**毫秒级模糊查价、零编译热更新**，告别繁琐的手动翻表！

---

## ✨ 核心特性

- 🔄 **云端定时全自动同步**：基于 GitHub Actions 每天清晨定时监控数码回收网，一旦有价格调整，自动提交推送最新 CSV 表格，**零云服务器成本**。
- ⚡ **毫秒级模糊即输即查**：本地工具内置智能模糊匹配引擎，自动忽略大小写、空格与破折号（如输入 `15pro`、`fold5`、`reno11` 瞬间出价）。
- 📦 **软件与数据完全解耦**：桌面程序与 `data/` 目录下的 CSV 表格完全分离。更新报价只需拉取最新代码或替换文件，**无需重新打包 EXE**。
- 🔍 **双击查看全量质检细则**：支持各品牌特有报价梯队（苹果无ID版、三星大/小老化档位、折痕扣减、镜头刮花扣款等），双击任意行即可弹窗展开完整条款。
- 🖥️ **原生零依赖与高分屏优化**：GUI 仅依赖 Python 原生标准库（Tkinter），无需额外安装庞大的第三方 GUI 框架，内置 Windows 高 DPI 适配，界面清晰不模糊。

---

## 📂 仓库目录结构

```text
sj-chax/
├── .github/
│   └── workflows/
│       ├── auto_sync.yml       # GitHub Actions 每天自动抓取并提交最新价格
│       └── build.yml           # (可选) 自动打包发布 Windows EXE
├── data/                       # 存放各品牌标准化的回收价格 CSV 表格
│   ├── Apple.csv
│   ├── OPPO.csv
│   ├── Vivo.csv
│   ├── Samsung.csv
│   ├── Huawei_Honor.csv
│   ├── Xiaomi_Redmi.csv
│   └── ...
├── phone_search.py             # 桌面快速查价 GUI 工具 (支持实时搜索、排序、弹窗)
├── update_prices.py            # 数码回收网数据抓取与解析引擎
├── requirements.txt            # 运行依赖 (爬虫依赖 requests, beautifulsoup4)
├── .gitignore                  # Git 忽略文件配置
└── README.md                   # 项目说明文档


## 🚀 快速上手
1. 本地运行查价小工具

由于桌面查价工具仅使用 Python 标准库，克隆后可直接双击或命令行启动：
code Bash

# 1. 克隆本仓库到本地
git clone https://github.com/uansla/sj-chax.git
cd sj-chax

# 2. 直接启动查询界面
python phone_search.py

    小技巧：在 Windows 上，您也可以将 phone_search.py 创建一个快捷方式放到桌面，双击即开即用。

2. 打包为绿色版独立 EXE（可选）

如果您希望分发给不熟悉 Python 的同事或直接制作独立的 .exe 文件：
code Bash

# 安装 PyInstaller 打包工具
pip install pyinstaller

# 编译为纯单文件应用程序 (注意：切勿添加 --add-data 参数，保持数据独立)
pyinstaller -F -w --name "手机回收价格秒查工具" phone_search.py

打包完成后，进入 dist/ 目录，将生成的 手机回收价格秒查工具.exe 与 data 文件夹放在同级目录即可随身携带或压缩分享：
code Text

📁 手机回收价格秒查工具/
├── 手机回收价格秒查工具.exe
└── 📁 data/
    ├── Apple.csv
    ├── OPPO.csv
    └── ...

🤖 自动化价格同步流程

本项目通过 .github/workflows/auto_sync.yml 实现每天全自动跟进市场价格：

    触发时间：每天 UTC 00:30（北京时间早晨 08:30）自动运行。

    运行机制：GitHub Actions 唤起 Python 爬虫 update_prices.py 扫描网站数据。

    自动提交：若比对发现价格或机型发生变动，自动执行 git commit 并推送到 main 分支；若无变动则静默退出。

⚙️ 仓库必要配置（关键）

为了让 GitHub Actions 机器人有权限向您的仓库推送更新好的 CSV，请务必开启写入权限：

    打开 GitHub 仓库，点击 Settings -> 左侧 Actions -> General；

    找到 Workflow permissions 区域；

    选择 Read and write permissions 并勾选下方的 Allow GitHub Actions to create and approve pull requests；

    点击 Save 保存。

📋 数据标准与回收等级说明

data/ 目录下的 CSV 表格均遵循统一的质量标准评级：
评级代号	等级定义	判定标准概述
K1 等级	开机屏好 / 靓好	开机正常进系统，内外屏完好，无压伤无老化，主板功能全正常；三星冷光屏外裂内好触摸正常算屏好。
H3 等级	开机屏坏	开机正常进系统，屏幕碎裂或缺失，主板无进水腐蚀、无断板、无大修、无严重变形。
F1 等级	不开机	主板无严重维修、无腐蚀压伤、芯片完好；整机零件无缺失（反复重启、进不去系统均算不开机）。
F3 等级	废板 · 整机	压伤严重、严重腐蚀进水、断线大修等，要求主芯片完好。

    注：苹果的“无ID靓板/不靓板”、三星的“微老化/重度老化扣款”、折叠屏的“折痕大扣费”等特例条款，均保存在各 CSV 的 备注 字段中，在查询工具中双击对应行即可弹出卡片完整查看。

🤝 贡献与支持

    提交新机型/反馈异常：欢迎提交 Issues 反馈错价或未收录的型号。

    改进检索工具：欢迎提交 Pull Requests 帮助扩充功能（如价格走势图、数据导出、微信小程序适配等）。

⚠️ 免责声明

    本项目内整理的回收数据均源自网络公开页面，仅供技术研究、二手行情参考与个人学习交流使用。

    实际回收成交以各大平台或回收商质检当日最终出价为准，请遵守各平台服务条款与法律法规，切勿用于商业欺诈或违规炒货。
