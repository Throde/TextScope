# TextScope

A lightweight Chinese & English corpus analysis toolkit featuring Firthian collocation, visualization, and semantic abstraction.

TextScope 是一个面向语料库的语言分析与可视化工具。它以 **弗思搭配（Firthian Collocation）** 为核心，在计算搭配强度的同时保留搭配词相对节点词的位置信息，形成二维共现分布，为下游语义研究提供更精细的表征。

- 当前发布版本：**V1.1.1**（Releases tag：`textscope_v1`）
- 支持语言：中文、English、日本語、Français、Deutsch

## 功能

- 弗思搭配抽取（Collocation Retrieval）
- 搭配可视化（Collocation Visualization）
- 相似性计算（Similarity Computation）
- 语义抽象（Semantic Abstraction）
- 多语种语料处理、词性/句法模式检索、KWIC 结果查看与导出

## 下载桌面应用（推荐）

如果你只是想使用软件，建议直接下载发行包，无需配置 Python 环境：

- 发布页：[TextScope_v1 / V1.1.1 Releases](https://github.com/Throde/TextScope/releases/tag/textscope_v1)
- Windows：[TextScope_V1.1.1_win.zip](https://github.com/Throde/TextScope/releases/download/textscope_v1/TextScope_V1.1.1_win.zip)
- macOS：[TextScope_V1.1.1_mac.dmg](https://github.com/Throde/TextScope/releases/download/textscope_v1/TextScope_V1.1.1_mac.dmg)

> 首次启动可能需要 1–2 分钟。macOS 版本尚未签名，如系统阻止运行，请前往「系统设置 → 隐私与安全性」手动允许。

Releases 页面同时包含版本说明、功能介绍和下列手册链接。

## 使用手册

- English 👉 [TextScope: Installation and User Manual](https://p.kdocs.cn/s/XYZUATRFADQGI)
- 中文 👉 [TextScope 安装及使用手册](https://p.kdocs.cn/s/4XJN4TJFADQGI)

---

## 开发者指南

### 目录结构

| 路径 | 说明 |
| --- | --- |
| `app.py` | 程序入口：启动闪屏、初始化资源/语言、创建主窗口与 Tab 页面 |
| `fancy_splash.py` | 启动时的轻量 Splash 动画 |
| `core_functions/collocation_ui.py` | 四个功能页面的 UI：搭配抽取、可视化、相似性、语义抽象 |
| `core_functions/collocation_func.py` | 核心算法：搭配抽取、关联度计算、可视化、相似性、语义抽象 |
| `core_functions/settings_ui.py` | 设置页面：界面语言、模型路径等配置，读写 `settings.json` |
| `core_functions/utils/` | 通用工具：资源定位、语料读取、spaCy 封装、语言模式检索、UI 基类、进度汇报、字体探测 |
| `core_functions/textalloc/` | 可视化用的文本布局 / 标签避让算法 |
| `data/` | 测试语料与示例文本（中/英/日/法/德） |
| `json_data/` | 预计算的结果样例（JSON） |
| `models/` | 内置 spaCy 语言模型（zh/en/ja/fr/de） |
| `fonts/` | 随包分发的 Noto Sans SC 字体，保证图表中文显示 |
| `langs/` | 英文翻译文件 `en.ts` / `en.qm` |
| `nltk_data/` | 随包分发的 NLTK 数据 |
| `settings.json` | 外部可替换配置：语言、样式、各语种自定义模型路径 |
| `bash_rec.txt` | 本地化编译与打包命令备忘 |
| `textscope.spec` | PyInstaller 打包配置 |
| `make_dmg.sh` | macOS DMG 制作脚本 |

### 从源码运行

需要 Python 3.11。仓库不包含虚拟环境，请自行创建：

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

内置模型位于 `models/`，`settings.json` 中 `model_paths` 默认为 `null`，表示使用内置模型。首次加载 spaCy 3.7.x 训练的模型时，在 spaCy 3.8.x 下可能出现 `[W095]` 兼容性提示；实测功能正常，可忽略。

### 关键模块说明

- `resource_path(type, *parts)`：统一处理开发环境和 PyInstaller 打包环境的资源路径；`in` 指向内置资源，`ex` 指向可外部替换的配置。
- `SpacyAPI`：负责加载对应语种模型、设置分词规则、执行 pipeline，并提供相似度等接口。
- `read_data()`：读取整目录、单文件或段落列表，并做文本预处理后返回 spaCy `Doc`。
- `LingPatternSearcher` / `Query`：基于 spaCy `DependencyMatcher` 与 `PhraseMatcher` 的词形、词性、句法关系检索。
- `PageWidget`：页面基类，封装后台线程、进度条、表格、KWIC 视图和导入导出。
- `ProgressReporter`：支持多层子区间的进度映射，便于把底层算法进度回传到 UI。
- `collocation_func.py` 中的 `FirthianCollocation`、`CollocationRetriever`、`ConcordanceSearcher` 是主要算法入口。

### 本地化

源文件使用中文，`self.tr()` 标记需要翻译的 UI 文本。按 `bash_rec.txt`：

```bash
pyside6-lupdate app.py core_functions/settings_ui.py core_functions/collocation_ui.py \
  core_functions/collocation_func.py core_functions/utils/page.py \
  core_functions/utils/spacy_api.py core_functions/utils/lang_ptn_searcher.py \
  -ts langs/en.ts -no-obsolete

pyside6-lrelease langs/en.ts
```

### 打包

```bash
pyinstaller textscope.spec
```

产物默认输出到 `dist/`，该目录以及 `build/` 已加入 `.gitignore`。构建产物通过 GitHub Releases 发布，不纳入源码仓库。

---

README 中的下载链接、手册链接与功能说明整理自本仓库 [Releases 页面](https://github.com/Throde/TextScope/releases/tag/textscope_v1)。
