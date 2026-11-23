# ui.py
# -*- coding: utf-8 -*-
import os
import json

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, 
    QMessageBox, QFileDialog
)
from PySide6.QtGui import QTextCursor

from .utils.page import PageWidget
from .utils.common import APP_VERSION
from .utils.common import resource_path, get_sys_lang
from .utils.common import DEFAULT_MODELS

from string import Template


# =========== 设置页 ===========
class SettingsPage(PageWidget):

    # 用于在内存中暂存用户的路径设置： e.g. {"zh": "C:/...", "en": None (代表使用内置)}
    _model_paths = {}

    QSS_TEMPLATE = Template(r"""
        QWidget {
            font-family: "Segoe UI","Microsoft YaHei","PingFang SC";
            font-size: 14px;
            color: $text; 
        }

        /* Panels / tabs */
        QTabWidget::pane {
            border: 0;
            background: $panel_bg;
        }
        QTabBar::tab { padding: 8px 16px; margin: 4px 2px 0px 2px; background: $tab_bg; color: $tab_text; }
        QTabBar::tab:hover { background: $tab_hover; }
        QTabBar::tab:selected { background: $tab_selected_bg; color: $tab_selected_text; }

        /* Buttons */
        QPushButton { background: $btn_bg; color: $btn_text; border: 0; border-radius: 10px; padding: 8px 12px; }
        QPushButton:hover { background: $btn_hover; }
        QPushButton:pressed { background: $btn_pressed; }
        QPushButton:disabled { background: $btn_disabled_bg; color: $btn_disabled_text; }

        /* Inputs */
        QLineEdit, QComboBox {
            padding: 6px 8px;
            border: 1px solid $input_border;
            border-radius: 8px;
            background: $input_bg;
            color: $text;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid $focus_border;
        }

        /* Multi-line editors */
        QTextEdit, QPlainTextEdit, QTextBrowser {
            background: $input_bg;
            color: $text;
            border: 1px solid $input_border;
            border-radius: 8px;
            padding: 6px 8px;
        }
        QTextEdit:disabled, QPlainTextEdit:disabled, QTextBrowser:disabled {
            background: $disabled_bg;
            color: $disabled_text;
        }

        /* Combo popup */
        QComboBox QAbstractItemView {
            background: $input_bg;
            border: 1px solid $input_border;
            selection-background-color: $list_sel_bg;
            selection-color: $list_sel_text;
        }

        /* Spin boxes */
        QSpinBox, QDoubleSpinBox, QAbstractSpinBox {
            background: $input_bg;
            color: $text;
            border: 1px solid $input_border;
            border-radius: 8px;
        }
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
            width: 16px;
        }

        /* Progress */
        QProgressBar {
            border: 1px solid $pb_border;
            background: $pb_bg;
            border-radius: 8px;
            text-align: center;
            height: 18px;
            color: $pb_text;
        }
        QProgressBar::chunk {
            background-color: $pb_chunk;
            border-radius: 8px;
        }

        /* Labels */
        QLabel.title {
            font-size: 18px;
            font-weight: 600;
            color: $title_text;
        }
        QLabel.hint  {
            color: $hint_text;
            font-size: 12px;
        }

        /* Tables */
        QTableWidget {
            background-color: $input_bg;        /* 强制背景白色 */
            color: $text;                   /* 强制文字黑色 */
            alternate-background-color: #F5F5F5; /* 设置隔行变色的浅灰色 */
            selection-background-color: #0078D7; /* (可选) 设置选中行的蓝色背景 */
            selection-color: white;         /* (可选) 设置选中行的白色文字 */
        }
        QHeaderView::section {
            background-color: #E0E0E0;      /* 表头背景灰白 */
            color: black;                   /* 表头文字黑 */
            border: 1px solid $input_border;/* 表头边框 */
        }
                            
        /* 多选对话框 */
        QDialog.MultiSelectDialog {
            background: $panel_bg;
            color: $text;
        }
        /* 列表区域 */
        /* QDialog.MultiSelectDialog QListWidget {
            background: $input_bg;
            color: $text;
            border: 1px solid $input_border;
            border-radius: 8px;
            alternate-background-color: #F6F6F6;
        } */
        QDialog.MultiSelectDialog QListWidget::item { padding: 6px 8px; }
        QDialog.MultiSelectDialog QListWidget::item:selected {
            background: $list_sel_bg;
            color: $list_sel_text;
        }
        QDialog.MultiSelectDialog QListWidget::item:hover {
            background: $list_sel_bg;
        }
        """)

    def __init__(self):
        super().__init__(
            title=self.tr("系统设置"),
            hint=self.tr("配置界面显示、计算模型与资源等选项。"),
            view_type=["str"],
            save_type="str" # 提供 self.save_btn
        )

        self.styles = {
            "classic": self.tr("经典黑白"), # 内部标签:显示文本
            "prussian_blue": self.tr("普鲁士蓝"),
            "mint_green": self.tr("清新薄荷"),
            "rose_quartz": self.tr("玫瑰砖粉"),
            "amber_glow": self.tr("温暖琥珀"),
            "zen": self.tr("极致简约"),
        }

        self.app_info = {
            self.tr("软件名称"): self.tr("TextScope 文本处理工具"),
            self.tr("软件版本"): APP_VERSION,
            self.tr("开发作者"): ",".join([self.tr("唐旭日"), self.tr("刘道焕")]),
            self.tr("归属单位"): self.tr("华中科技大学"),
            self.tr("软著编号"): "",
            self.tr("联系方式"): "liudh@hust.edu.cn"
        }

        self.cite_items = {
            self.tr("弗思搭配"): "Liu, D., & Tang, X. (2024). Comparative linguistic analysis with Firthian collocations: Cases of synonym differentiation and proficiency assessment. Lingua, 306, 103755. https://doi.org/10.1016/j.lingua.2024.103755"
        }

        # 向 self.form 添加输入组件
        form_layout = QFormLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)

        # 左侧：交互区 --------------
        # 显示语言
        lang_layout = self._add_row(form_layout, 
                                    self.tr("显示语言"), 
                                    self.tr("系统界面显示的语言。"))
        self.lang_combo = QComboBox()
        # 【重要优化】使用 addItem(text, userData) 分离显示文本和逻辑值
        # 这样以后界面显示 "Chinese/English" 时，逻辑判断依然可以用 "zh/en"
        self.lang_combo.addItem("中文", "zh")
        self.lang_combo.addItem("English", "en")
        # 动态获取当前应该显示的语言索引 
        current_lang = get_sys_lang()
        idx = self.lang_combo.findData(current_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        lang_layout.addWidget(self.lang_combo)
        
        style_layout = self._add_row(form_layout, 
                                     self.tr("系统配色"), 
                                     self.tr("系统界面显示的主题色。"))
        self.style_combo = QComboBox()
        for style_data, style_name in self.styles.items():
            self.style_combo.addItem(style_name, userData=style_data)
        self.style_combo.setCurrentIndex(0)  # 默认第一个
        self.style_combo.currentIndexChanged.connect(self._on_style_changed) # 绑定：选择变化即刻换肤
        style_layout.addWidget(self.style_combo)

        # 添加分隔线
        self._add_split_line(form_layout)

        # 模型配置
        # 初始化暂存字典
        self._model_paths = {k: None for k in DEFAULT_MODELS.keys()}
        # 模型配置区域
        # model_title_row = self._add_row(form_layout, "语言模型配置", 
        #     "默认使用软件内置的小型模型(sm)。如需更高精度，可下载 spaCy 大型模型并指定文件夹路径。")
        # 使用循环或逐个添加 5 个语种的配置行
        langs = [
            ("zh", self.tr("中文模型")),
            ("en", self.tr("英语模型")),
            ("ja", self.tr("日语模型")),
            ("fr", self.tr("法语模型")),
            ("de", self.tr("德语模型"))
        ]
        # 存储 UI 控件引用的字典，方便 load/save 时读写
        self._ui_path_edits = {} 
        for lang_code, label_text in langs:
            model_dir_layout = self._add_row(form_layout, 
                                             label_text, 
                                             self.tr("搭配提取中实际使用的语言模型。若想更换更强大的模型，请参考右侧使用手册进行下载与替换。"))
            self._ui_path_edits[lang_code] = self._add_edit_btn(model_dir_layout, 
                                                  edit_placeholder=self.tr("模型存放目录"),
                                                  buttons=[
                                                      # 将 lang_code 赋值给默认参数 lc
                                                      (self.tr("修改"), lambda checked=False, lc=lang_code: self._on_change_model_path(lc)),
                                                      (self.tr("重置"), lambda checked=False, lc=lang_code: self._on_reset_model_path(lc))
                                                    ])

        # 右侧：文本区 --------------
        copyright_text = self.tr("版权声明") + "\n\n"
        copyright_text += self.tr("【软件信息】") + "\n"
        for k, v in self.app_info.items():
            if v:
                copyright_text += f"{k}: {v}\n"
        copyright_text += "\n"
        copyright_text += self.tr("【使用规范】") + "\n" + self.tr("若您的研究使用了此软件提供的功能，请在发表中进行适当引用：") + "\n"
        for k, v in self.cite_items.items():
            if v:
                copyright_text += f"{k}: {v}\n"
        copyright_text += "\n"
        copyright_text += self.tr("【文档手册】") + "\n" + self.tr("了解本工具的详细使用说明：") + "\n"
        copyright_text += self.tr("https://p.kdocs.cn/s/4XJN4TJFADQGI") # 中英各有一份，这里默认中文

        # 将内容填充到输出框里
        self.str_view.clear()
        self.str_view.setPlainText(copyright_text)
        self.str_view.moveCursor(QTextCursor.Start)

        # 修改保存按钮的内容 --------------
        self.save_btn.setText(self.tr("保存设置"))
        self.save_btn.clicked.disconnect() # 断开旧连接
        self.save_btn.clicked.connect(self.save_settings)
        self.save_btn.setEnabled(True)
        
        # 初始化：首次运行写入 / 否则读取并恢复
        self._init_settings()

    # ---------- 辅助方法 ----------
    def _settings_path(self):
        """settings.json 默认放在程序目录（可执行所在目录）"""
        return resource_path("ex", "settings.json")

    def _init_settings(self):
        """若无文件则创建；若有则读取并恢复 UI。"""
        path = self._settings_path()
        
        if not os.path.exists(path):
            # 首次运行：用默认 UI 状态写一个文件
            try:
                cfg = self.get_settings(default=True)
                # 确保目录存在（以防你未来把路径放到子目录）
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=4)
                
                # 然后重新读取默认参数
                self.load_settings(path)
                    
            except Exception as e:
                QMessageBox.warning(self, self.tr("初始化失败"), self.tr("写入默认设置失败：") + str(e))
            
        else:
            # 已存在：读取并恢复
            try:
                self.load_settings(path)
            except Exception as e:
                QMessageBox.warning(self, self.tr("读取失败"), self.tr("读取设置 settings.json 失败：") + str(e))

    # ---------- 设置读/写 ----------
    def get_settings(self, default=False) -> dict:
        """导出当前设置数据，便于持久化。"""
        if not default:
            return {
                "language": self.lang_combo.currentData(), # "zh" or "en"
                "style": self.style_combo.currentData(),  # e.g. "classic"
                "model_paths": self._model_paths # None for built-in, else using DIY path
            }
        else:
            # 默认配置不再硬编码 en 或 zh，而是同步系统探测逻辑
            return {
                "language": get_sys_lang(),
                "style": "classic",
                "model_paths": {k: None for k in DEFAULT_MODELS.keys()}
            }

    def load_settings(self, path: str):
        """从配置恢复 UI。键缺省时保持当前。"""
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            
        # 语言 ----------
        lang = cfg.get("language")
        if lang in ("zh", "en"):
            idx = self.lang_combo.findData(lang)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)

        # 主题 ----------
        style_name = cfg.get("style") or "classic" # 默认经典样式
        style_name = self.styles.get(style_name, "classic") # 映射为显示文本
        idx = self.style_combo.findText(style_name)
        if idx >= 0:
            self.style_combo.setCurrentIndex(idx)
        # 立即应用一次（避免只显示索引未实际换肤）
        self._apply_style(self.style_combo.currentData())

        # 模型偏好 ----------
        saved_paths = cfg.get("model_paths", {})
        for lang in DEFAULT_MODELS.keys():
            # 读取配置，若无则默认为 None
            p = saved_paths.get(lang)
            # 校验路径是否存在，若不存在则回退到内置
            if p and not os.path.exists(p):
                p = None
            
            self._model_paths[lang] = p
            self._update_path_display(lang)

    @Slot()
    def save_settings(self):
        """将当前状态写回本地 settings.json"""
        cfg = self.get_settings()
        try:
            path = self._settings_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, self.tr("提示"), self.tr("设置保存成功！语言更改将在软件重启后生效。"))
        except Exception as e:
            QMessageBox.warning(self, self.tr("提示"), self.tr("设置保存失败：") + str(e))
    
    # ---------- 模型设置相关 ----------
    def _on_change_model_path(self, lang_code):
        """点击修改按钮：选择文件夹"""
        # 默认从当前已选目录开始，或者从程序根目录开始
        start_dir = self._model_paths.get(lang_code) or resource_path("ex")
        
        # 弹出文件夹选择框
        new_dir = QFileDialog.getExistingDirectory(self, self.tr("选择 %s 模型文件夹") % lang_code, start_dir)
        
        if new_dir:
            # 校验1：检查目录名语言前缀是否匹配
            dir_name = os.path.basename(new_dir)
            if not dir_name.lower().startswith(f"{lang_code}_"):
                QMessageBox.warning(self, self.tr("语言不匹配"), 
                                    self.tr("所选模型似乎不是 %s 语种的模型：模型目录名称必须以 '%s_' 开头（例如：%s_core_web_sm）。") % (lang_code, lang_code, lang_code))
                return
            # 校验2：目录下是否有 config.cfg 或 meta.json (spaCy 模型特征)
            if not (os.path.exists(os.path.join(new_dir, "config.cfg")) or 
                    os.path.exists(os.path.join(new_dir, "meta.json"))):
                QMessageBox.warning(self, self.tr("无效模型"), self.tr("所选文件夹似乎不是一个有效的 spaCy 模型目录（未找到 config.cfg 或 meta.json 文件）。"))
                return

            # 更新内存数据
            self._model_paths[lang_code] = new_dir
            # 更新 UI 显示
            self._update_path_display(lang_code)

    def _on_reset_model_path(self, lang_code):
        """点击重置按钮：设为 None"""
        self._model_paths[lang_code] = None
        self._update_path_display(lang_code)

    def _update_path_display(self, lang_code):
        """根据 _model_paths 更新输入框文字"""
        path = self._model_paths.get(lang_code)
        edit = self._ui_path_edits[lang_code]
        
        if path:
            # 显示用户自定义路径，并设为黑色文字
            edit.setText(path)
            edit.setCursorPosition(0)
            edit.setToolTip(self.tr("自定义模型路径：") + f"{path}")
        else:
            # 显示内置提示，设为灰色文字或留空显示 placeholder
            edit.setText(self.tr("内置模型") + f" ({DEFAULT_MODELS[lang_code]})")
            edit.setCursorPosition(0)
            edit.setToolTip(self.tr("当前使用软件内置的轻量级模型（%s）。") % DEFAULT_MODELS[lang_code])

    # ---------- 样式相关 ----------
    def _on_style_changed(self, index: int):
        if index < 0: return
        # 获取当前选中的 userData (即 "classic", "prussian_blue" 等)
        style_code = self.style_combo.itemData(index)
        # 将内部代码传给应用逻辑
        self._apply_style(style_code)

    def _apply_style(self, name: str):
        """将主题应用到整个应用（运行时可随时调用）"""
        app = QApplication.instance()
        if not app:
            return
        # name：显示名称（如经典样式）
        app.setStyleSheet(self._get_qss(name))

    def _get_qss(self, name: str) -> str:
        """QSS"""
        if name == "classic":
            # 当前在主窗口里用的那版（可按需精简/修改）
            theme = {
                "text": "#1E1E1E",
                "panel_bg": "#FAFAFA",
                "tab_bg": "#F2F2F2",
                "tab_text": "#1E1E1E",
                "tab_hover": "#E5E5E5",
                "tab_selected_bg": "#1E1E1E",
                "tab_selected_text": "#FFFFFF",

                "btn_bg": "#1E1E1E",
                "btn_text": "#FFFFFF",
                "btn_hover": "#2C2C2C",
                "btn_pressed": "#141414",
                "btn_disabled_bg": "#C8C8C8",
                "btn_disabled_text": "#F0F0F0",

                "input_bg": "#FFFFFF",
                "input_border": "#D3D3D3",
                "focus_border": "#1E1E1E",
                "disabled_bg": "#F5F5F5",
                "disabled_text": "#9E9E9E",

                "list_sel_bg": "#EAEAEA",
                "list_sel_text": "#1E1E1E",

                "pb_border": "#D3DEE9",
                "pb_bg": "#F3F7FC",
                "pb_text": "#1E293B",
                "pb_chunk": "#2FA86E",

                "title_text": "#1E1E1E",
                "hint_text": "#6B6B6B",
            }
            return self.QSS_TEMPLATE.substitute(theme)

        elif name == "prussian_blue":
            # 低饱和普鲁士蓝主题
            theme = {
                "text": "#1E1E1E",
                "panel_bg": "#F3F7FC",
                "tab_bg": "#DDE6F1",
                "tab_text": "#1E293B",
                "tab_hover": "#CBD9E8",
                "tab_selected_bg": "#224C7A",
                "tab_selected_text": "#F5FAFF",

                "btn_bg": "#224C7A",
                "btn_text": "#F5FAFF",
                "btn_hover": "#1B3F66",
                "btn_pressed": "#163554",
                "btn_disabled_bg": "#9FB3C8",
                "btn_disabled_text": "#E8EEF5",

                "input_bg": "#FFFFFF",
                "input_border": "#D3DEE9",
                "focus_border": "#3A6EA5",
                "disabled_bg": "#F5F5F5",
                "disabled_text": "#9E9E9E",

                "list_sel_bg": "#E4EEF8",
                "list_sel_text": "#1E293B",

                "pb_border": "#D3DEE9",
                "pb_bg": "#F3F7FC",
                "pb_text": "#1E293B",
                "pb_chunk": "#2FA86E",

                "title_text": "#1E293B",
                "hint_text": "#6B7A8C",
            }
            return self.QSS_TEMPLATE.substitute(theme)

        elif name == "mint_green":
            # 清新薄荷绿主题
            theme = {
                "text": "#1E1E1E",
                "panel_bg": "#F4FAF6",
                "tab_bg": "#E5F3EA",
                "tab_text": "#1E293B",
                "tab_hover": "#CDE9D7",
                "tab_selected_bg": "#4C9B6C",
                "tab_selected_text": "#FFFFFF",

                "btn_bg": "#4C9B6C",
                "btn_text": "#FFFFFF",
                "btn_hover": "#41885F",
                "btn_pressed": "#357551",
                "btn_disabled_bg": "#A9CDB3",
                "btn_disabled_text": "#E8F2EC",

                "input_bg": "#FFFFFF",
                "input_border": "#CDE4D2",
                "focus_border": "#4C9B6C",
                "disabled_bg": "#F5F5F5",
                "disabled_text": "#9E9E9E",

                "list_sel_bg": "#E0F3E7",
                "list_sel_text": "#1E293B",

                "pb_border": "#D3DEE9",
                "pb_bg": "#F3F7FC",
                "pb_text": "#1E293B",
                "pb_chunk": "#2FA86E",

                "title_text": "#1E293B",
                "hint_text": "#6B7A8C",
            }
            return self.QSS_TEMPLATE.substitute(theme)
        
        elif name == "rose_quartz":
            # 玫瑰砖粉主题
            theme = {
                "font_family": '"Segoe UI","Microsoft YaHei","PingFang SC"',
                "text": "#1E1E1E",

                "panel_bg": "#FDF5F4",
                "tab_bg": "#FBE9E4",
                "tab_text": "#473F3F",
                "tab_hover": "#F4D9D2",
                "tab_selected_bg": "#D77C6E",
                "tab_selected_text": "#FFFFFF",

                "btn_bg": "#D77C6E",
                "btn_text": "#FFFFFF",
                "btn_hover": "#C26D60",
                "btn_pressed": "#AC5E53",
                "btn_disabled_bg": "#E8B9B0",
                "btn_disabled_text": "#FAECE7",

                "input_bg": "#FFFFFF",
                "input_border": "#E7C8BD",
                "focus_border": "#D77C6E",
                "disabled_bg": "#F5F5F5",
                "disabled_text": "#9E9E9E",

                "list_sel_bg": "#FBE4DF",
                "list_sel_text": "#473F3F",

                "pb_border": "#D3DEE9",
                "pb_bg": "#F3F7FC",
                "pb_text": "#1E293B",
                "pb_chunk": "#2FA86E",

                "title_text": "#473F3F",
                "hint_text": "#7A6F6F",
            }
            return self.QSS_TEMPLATE.substitute(theme)
        
        elif name == "amber_glow":
            # 温暖琥珀橙主题
            theme = {
                "font_family": '"Segoe UI","Microsoft YaHei","PingFang SC"',
                "text": "#1E1E1E",

                "panel_bg": "#FFF9F2",
                "tab_bg": "#FFF3E1",
                "tab_text": "#4A3B20",
                "tab_hover": "#FFE3B8",
                "tab_selected_bg": "#D48A1F",
                "tab_selected_text": "#FFFFFF",

                "btn_bg": "#D48A1F",
                "btn_text": "#FFFFFF",
                "btn_hover": "#BF7A1C",
                "btn_pressed": "#A96818",
                "btn_disabled_bg": "#E8C594",
                "btn_disabled_text": "#FFF5E6",

                "input_bg": "#FFFFFF",
                "input_border": "#E8D5B8",
                "focus_border": "#D48A1F",
                "disabled_bg": "#F5F5F5",
                "disabled_text": "#9E9E9E",

                "list_sel_bg": "#FFE9C7",
                "list_sel_text": "#4A3B20",

                "pb_border": "#D3DEE9",
                "pb_bg": "#F3F7FC",
                "pb_text": "#1E293B",
                "pb_chunk": "#2FA86E",

                "title_text": "#4A3B20",
                "hint_text": "#7B6B55",
            }
            return self.QSS_TEMPLATE.substitute(theme)

        elif name == "zen":
            # 回到“系统默认外观”，恢复到未设置样式的状态
            return ""
    