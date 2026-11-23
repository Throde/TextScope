# encoding: utf-8
# 供全局使用的函数和参数
APP_VERSION = "V1.1.1"

# 内置各语种的fallback spacy模型
DEFAULT_MODELS = {
    "zh": "zh_core_web_sm-3.7.0",
    "en": "en_core_web_sm-3.7.1",
    "ja": "ja_core_news_sm-3.7.0",
    "fr": "fr_core_news_sm-3.7.0",
    "de": "de_core_news_sm-3.7.0"
}

import sys, os
def resource_path(type: str="in", *path_parts: str) -> str:
    """
    返回内部/外部资源路径。兼容开发环境与打包环境，兼容mac系统与windows系统。
    """
    base_dir = ""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包成可分发包之后的模式
        if type == "in":
            # 内部固定资源路径：onefile & onedir 都有 _MEIPASS 解包目录
            base_dir = sys._MEIPASS
        elif type == "ex":
            # 外部可替换资源路径
            if sys.platform == "darwin":
                # macOS系统：YourApp.app/Contents/MacOS/YourApp 往上多倒3级，回到.app所在层级
                base_dir = os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(sys.executable)
                        )
                    )
                )
            else:
                # Windows系统：直接就在 YourApp.exe 同级检索资源
                base_dir = os.path.dirname(sys.executable)
        else:
            raise ValueError(f"resource_path type must be 'in' or 'ex', got: {type!r}")
    else:
        # 正常 python 运行（python app.py）：直接基于当前入口文件所在目录
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base_dir, *path_parts)


import json
from PySide6.QtCore import QLocale
def get_sys_lang():
    """
    获取当前的运行UI语言。return: "zh" or "en"
    """
    lang = None

    # 1. 优先尝试从配置文件读取 settings.json 设置的语言
    settings_path = resource_path("ex", "settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                lang = cfg.get("language")
        except:
            pass

    # 2. 如果配置文件里没有设置语言（或是第一次启动），则检测用户电脑的系统语言
    if lang not in ("zh", "en"):
        system_locale = QLocale.system().name() # 获取系统区域代码，如 "zh_CN", "zh_TW", "en_US"
        # print(system_locale)
        lang = "zh" if system_locale.startswith("zh") else "en"
    
    return lang
