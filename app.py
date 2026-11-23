# app.py
# -*- coding: utf-8 -*-
# ========================
# 顶级系统设置
import sys
import logging
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)    # 屏蔽 matplotlib 的字体查找信息

from PySide6.QtWidgets import (
    QApplication, QMainWindow, 
    QWidget, QTabWidget, QVBoxLayout, QLabel
)
# from PySide6.QtGui import QIcon
app = QApplication(sys.argv)


# ========================
# 起一个极轻量的 Splash 小图
from fancy_splash import FancySplash
from core_functions.utils.common import APP_VERSION
from core_functions.utils.common import resource_path, get_sys_lang

splash = FancySplash(title="TextScope", subtitle=APP_VERSION)
splash.show()

splash.set_progress(5, "Launching...")
QApplication.processEvents() # 强制刷新 UI


# ========================
# 统一应用资源路径搜索设置
from nltk import data as nltk_data
# Matplotlib 中文字体资源
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

def check_resources():
    # -------------
    # 1.配置 NLTK 数据路径
    nltk_path = resource_path("in", "nltk_data")
    nltk_data.path.clear()
    nltk_data.path.append(nltk_path)

    # -------------
    # 2.加载随包分发的默认字体作为plt初始字体
    font_path = resource_path("in", "fonts", "NotoSansSC-Regular.ttf")
    fm.fontManager.addfont(font_path)
    # 指定默认族类（本app默认用 NotoSansSC-Regular 绘图）
    plt.rcParams["font.family"] = ["Noto Sans SC"]
    plt.rcParams["axes.unicode_minus"] = False # 避免负号 '-' 显示成方块
    
# 在import spacy之前就要检查资源
check_resources()

splash.set_progress(15, "Initializing resources...")
QApplication.processEvents() # 强制刷新 UI


# ========================
# 加载语言资源
from PySide6.QtCore import QTranslator

def load_app_language(app):
    """
    加载语言文件
    """
    lang_code = get_sys_lang()  # 'en' 或 'zh'

    translator = QTranslator()
    
    # 如果是中文，尝试移除翻译器（恢复默认源码显示），或者加载 zh_CN.qm
    # 假设源码就是中文，选中文时只需移除英文翻译器
    if lang_code == 'zh':
        # 这里需要确保持有 translator 的引用，或者在全局变量中移除旧的
        pass 
        
    elif lang_code == 'en':
        # 加载生成的 .qm 文件
        qm_path = resource_path("in", "langs", "en_US.qm")
        if translator.load(qm_path):
            app.installTranslator(translator)
            # 保持 translator 引用，防止被垃圾回收
            app._translator = translator 
            # print(f"Loaded English: {qm_path}")
        else:
            # print(f"Failed to load: {qm_path}")
            pass

# 加载对应的语言包
load_app_language(app)

splash.set_progress(30, "Initializing resources...")
QApplication.processEvents() # 强制刷新 UI


# ========================
# 主界面、大包体连锁引用
from core_functions.collocation_ui import FCRetrievePage, FCVisualPage, FCSimilarityPage, FCAbstractionPage
from core_functions.settings_ui import SettingsPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"TextScope {APP_VERSION}")
        # self.setWindowIcon(QIcon("assets/icon.png"))
        self.resize(1200, 800)
        self.setMinimumSize(800, 800) # 窗口不能被压到太小

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1：弗思搭配抽取
        self.subtabs_fc = QTabWidget()  # 二级子Tab容器
        self.tabs.addTab(self.subtabs_fc, self.tr("弗思搭配"))
        self._create_subtab_page(self.subtabs_fc,
                                 (self.tr("搭配抽取"), FCRetrievePage()),
                                 (self.tr("搭配可视化"), FCVisualPage()),
                                 (self.tr("相似性计算"), FCSimilarityPage()),
                                 (self.tr("语义抽象"), FCAbstractionPage()))
        self.subtabs_fc.setCurrentIndex(0)  # 默认打开第一个子页

        # Tab 2：命题抽取
        # self.subtabs_prop = QTabWidget()
        # self.tabs.addTab(self.subtabs_prop, "命题抽取")
        # self._create_subtab_page(self.subtabs_prop,
        #                          ("命题功能1", None), 
        #                          ("命题功能2", None),
        #                          ("命题功能3", None))
        # self.subtabs_prop.setCurrentIndex(0)

        # Tab 3：设置
        self.subtabs_prop = QTabWidget()
        self.tabs.addTab(self.subtabs_prop, self.tr("设置"))
        self._create_subtab_page(self.subtabs_prop,
                                 (self.tr("系统设置"), SettingsPage()))
        self.subtabs_prop.setCurrentIndex(0)

        self.tabs.currentChanged.connect(self._on_main_tab_changed)
        self.tabs.setCurrentIndex(0)  # 默认第一个

    # 切换一级 Tab 时：自动回到其第一个子页
    def _on_main_tab_changed(self, idx: int):
        current = self.tabs.widget(idx)
        if isinstance(current, QTabWidget):
            current.setCurrentIndex(0)

    def _create_subtab_page(self, tabWidget: QTabWidget, *pages: tuple[str, QWidget]):
        for sub_title, page_widget in pages:
            if page_widget != None:
                tabWidget.addTab(page_widget, sub_title)
            else:
                # 为None，暂时做个占位页面
                page = QWidget()
                layout = QVBoxLayout(page)
                layout.addWidget(QLabel(f"（{sub_title} · 正在建设中）"))
                layout.addStretch()
                tabWidget.addTab(page, sub_title)
        return True

splash.set_progress(60, "Loading pages...")
QApplication.processEvents() # 强制刷新 UI


def main():
    win = MainWindow()

    splash.set_progress(100, "Ready.")
    QApplication.processEvents() # 让用户看一眼 100%
    
    win.show()
    splash.close() # 关闭 Splash

    sys.exit(app.exec())



if __name__ == "__main__":
    main()
