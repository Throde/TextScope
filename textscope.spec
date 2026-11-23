# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


APP_VERSION = "V1.1.1"


datas = [] # 复制非 Python 文件到最终程序目录，作为“资源文件”原样包含
hiddenimports = [] # import 不可见的 Python 模块
excludes = [ # 强力排除模块，减小体积
    # GUI / 交互环境
    'tkinter',
    'PyQt5', 'PyQt6', 'PySide2',
    'IPython', 'jupyter',

    # matplotlib 测试
    'matplotlib.tests',
    'matplotlib.testing',
    'matplotlib.backends.backend_tkagg',
    'matplotlib.backends.backend_gtk3agg',
    'matplotlib.backends.backend_qt4agg',
    'matplotlib.backends.backend_qt5agg',
    'matplotlib.backends.backend_pdf',
    'matplotlib.backends.backend_ps',
    'matplotlib.backends.backend_svg',
    'matplotlib.backends.backend_cairo',

    # 开发向工具
    'setuptools',
    'distutils',

    # 排除 PySide6 WebEngine 相关模块
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineQuick',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
]


# ====== 收集汉语分词的 spacy_pkuseg ======
datas += collect_data_files('spacy_pkuseg')  # 会把 dicts/default.pkl 等资源打包进去
hiddenimports += collect_submodules('spacy_pkuseg')

# ====== 收集日语分词的 sudachipy/sudachidict_core ======
datas += collect_data_files('sudachipy')
datas += collect_data_files('sudachidict_core')
hiddenimports += collect_submodules('sudachipy')
hiddenimports += collect_submodules('sudachidict_core')


# ====== 收集其他运行时的内部资源 ======
if os.path.exists('fonts'):
    datas.append(('fonts', 'fonts'))

if os.path.exists('models'):
    datas.append(('models', 'models'))

if os.path.exists('nltk_data'):
    datas.append(('nltk_data', 'nltk_data'))

if os.path.exists('langs'):
    datas.append(('langs', 'langs'))


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        # 告诉官方 hook 我们使用 Agg（可选，进一步减少探测）
        'matplotlib': {'backend': 'Agg'}
    },
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'TextScope_{APP_VERSION}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False, # UPX=True 体积小但解压略慢；关注启动速度可设 False
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # ✅ 隐藏控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

import sys
if sys.platform == 'darwin':
    # macOS专用：额外打包.app
    app = BUNDLE(
        exe,
        name=f'TextScope_{APP_VERSION}.app', # 产出 .app
        icon=None, # 可填 'resources/icon.icns'
        bundle_identifier='com.yourco.textscope',  # 可选
        info_plist={ # 可选，示例
            'NSHighResolutionCapable': 'True',
        },
        # mac 上如果暂不签名就保持 None；要签名再配置
        codesign_identity=None,
        entitlements_file=None,
    )