# ui.py
# -*- coding: utf-8 -*-
import os
import traceback

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QRadioButton, QButtonGroup, QComboBox, QCheckBox, 
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, 
    QFileDialog, QLineEdit, QDialog,
    QFormLayout, QMessageBox, 
)

from .collocation_func import CollocationRetriever, FirthianCollocation # 导入同目录下的模块
from .collocation_func import ConcordanceSearcher
from .utils.page import PageWidget, MultiSelectDialog
from .utils.fonts import CJK_LIST, LATIN_LIST
from .utils.progress_reporter import ProgressReporter

import json


# =========== 弗思搭配抽取 ===========
class FCRetrievePage(PageWidget):

    metrics = {
        "ΔP": "ΔP (Delta-P)", # 内部标签:显示文本
        "PMI": "PMI",
        "t-test": "t-test",
        "Chi-square-test": "Chi-square-test",
        "Phi-square-test": "Phi-square-test",
        "Dice": "Dice",
        "MI-like-3": "MI-like-3",
        "Log-likelihood-ratio": "Log-likelihood-ratio",
        "Poisson-stirling": "Poisson-stirling",
        "Jaccard": "Jaccard",
        "Local_MI": "Local_MI",
        "Minimum-sensitivity": "Minimum-sensitivity",
        "Fisher-exact-test": "Fisher-exact-test"
    }
    
    def __init__(self):
        super().__init__(
            title=self.tr("搭配抽取"),
            hint=self.tr("从语料中抽取弗思搭配，生成搭配数据并可视化呈现。"),
            view_type=["tbl", "fig", "str"], 
            subview_type="kwic",       # 下半部分：KWIC
            save_type="str"
        )

        self.langs = {
            "en": self.tr("英语 (EN)"),
            "zh": self.tr("汉语 (ZH)"), # 内部标签:显示文本
            "fr": self.tr("法语 (FR)"),
            "ja": self.tr("日语 (JA)"),
            "de": self.tr("德语 (DE)"),
        }

        self.POS_TAGS = [
            (self.tr("动词(VERB)"), "verb"),
            (self.tr("名词(NOUN)"), "noun"),
            (self.tr("形容词(ADJ)"), "adj"),
            (self.tr("副词(ADV)"), "adv"),
            (self.tr("专有名词(PROPN)"), "propn"),
            (self.tr("实词(CONTENT WORD)"), "content"),
            (self.tr("虚词(FUNCTION WORD)"), "function"),
        ]

        # 向 self.form 添加输入组件
        form_layout = QFormLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)

        # 语料语言
        lang_layout = self._add_row(form_layout, 
                                    self.tr("语料语言"), 
                                    self.tr("不同语言的预处理将需要使用对应的语言模型。模型资源可前往设置页进行配置。"))
        self.lang_combo = QComboBox()
        for lang_data, lang_name in self.langs.items():
            self.lang_combo.addItem(lang_name, userData=lang_data)
        lang_layout.addWidget(self.lang_combo)

        # 区分大小写子面板（仅拉丁文显示）
        lang_subform_layout_1 = self._add_subform(
            form_layout, 
            init_vis=True, 
            event_trigger=self.lang_combo.currentIndexChanged, # 关联到 self.lang_combo 选项
            show_if=[0,2,4] # 当 self.lang_combo 的值变更为 拉丁语系 时显示子面板
            )
        case_layout = self._add_row(lang_subform_layout_1, "", "")
        self.case_sensitive_chk = QCheckBox(self.tr("区分大小写"))
        self.case_sensitive_chk.setToolTip(self.tr("若取消勾选，则将所有大写字母统一转换为小写进行统计。"))
        self.case_sensitive_chk.setChecked(True)  # 默认 True
        case_layout.addWidget(self.case_sensitive_chk)
        case_layout.addStretch()

        # 词形还原复选框（除中文均显示）
        lang_subform_layout_2 = self._add_subform(
            form_layout, 
            init_vis=True, 
            event_trigger=self.lang_combo.currentIndexChanged, # 关联到 self.lang_combo 选项
            show_if=[0,2,3,4] # 当 self.lang_combo 的值变更为 非中文 时显示子面板
            )
        lemma_layout = self._add_row(lang_subform_layout_2, "", "")
        self.use_lemma_chk = QCheckBox(self.tr("词形还原"))
        self.use_lemma_chk.setToolTip(self.tr("若勾选，则将词语的各种变形形态统一归并为原形进行统计。"))
        self.use_lemma_chk.setChecked(True)     # 默认True
        lemma_layout.addWidget(self.use_lemma_chk)
        lemma_layout.addStretch()

        # 输入语料数据（两行），可选文件/目录
        input_layout = self._add_row(form_layout, 
                                     self.tr("语料数据"), 
                                     self.tr("指定输入语料文件或语料目录，可支持单个txt文件或整个文件夹。"))
        self.input_edit = self._add_edit_btn(input_layout, 
                                             edit_placeholder=self.tr("*.txt 或 目录路径"), 
                                             buttons=[
                                                 (self.tr("文件"), self.choose_input_file), 
                                                 (self.tr("目录"), self.choose_input_dir)
                                                 ])

        # 添加分隔线
        self._add_split_line(form_layout)

        # 节点词
        input_layout = self._add_row(form_layout, 
                                     self.tr("节点词"), 
                                     self.tr("要检索的中心词，即计算搭配时的核心目标词。"))
        self.node_word_edit = QLineEdit()
        self.node_word_edit.setPlaceholderText(self.tr("要检索的中心词"))
        input_layout.addWidget(self.node_word_edit)

        # 节点词性（可多选，默认全不选 = 不限制）
        node_pos_layout = self._add_row(form_layout, 
                                        self.tr("节点词性"), 
                                        self.tr("可多选。若不选，则不作词性限制。"))
        # 数据存储：选中值集合（tag集），空集合代表“不限制”
        self.node_pos_selected = set()
        self.node_pos_summary = self._add_edit_btn(node_pos_layout, 
                                                   edit_placeholder=self.tr("未选择（不限制）"), 
                                                   buttons=[
                                                       (self.tr("选择"), lambda: self._choose_pos(target="node"))
                                                       ])
        self._refresh_pos_summary(self.node_pos_selected, self.node_pos_summary)  # 初始化摘要

        # 添加分隔线
        self._add_split_line(form_layout)

        # 搭配算法
        metric_layout = self._add_row(form_layout, 
                                      self.tr("搭配算法"), 
                                      self.tr("用于计算搭配强度的统计指标。"))
        self.metric_combo = QComboBox()
        for metric_data, metric_name in self.metrics.items():
            self.metric_combo.addItem(metric_name, userData=metric_data)
        metric_layout.addWidget(self.metric_combo)

        # 窗口范围
        win_layout = self._add_row(form_layout, 
                                   self.tr("窗口范围"), 
                                   self.tr("搭配提取时的左右窗口大小（例如左5+右5表示在目标词左右各取5词）。"))
        self.win_left = QSpinBox()
        self.win_left.setRange(1, 5)
        self.win_left.setValue(5)   # 默认值可调
        self.win_right = QSpinBox()
        self.win_right.setRange(1, 5)
        self.win_right.setValue(5)   # 默认值可调
        win_layout.addWidget(QLabel(self.tr("左")))
        win_layout.addWidget(self.win_left)
        win_layout.addWidget(QLabel(self.tr("右")))
        win_layout.addWidget(self.win_right)
        win_layout.addStretch()

        # 搭配词性（可多选，默认全不选 = 不限制）
        coll_pos_layout = self._add_row(form_layout, 
                                        self.tr("搭配词性"), 
                                        self.tr("可多选。若不选，则不作词性限制。"))
        # 数据存储：选中值集合（tag集），空集合代表“不限制”
        self.coll_pos_selected = set()
        self.coll_pos_summary = self._add_edit_btn(coll_pos_layout, 
                                                   edit_placeholder=self.tr("未选择（不限制）"), 
                                                   buttons=[
                                                       (self.tr("选择"), lambda: self._choose_pos(target="coll"))
                                                       ])
        self._refresh_pos_summary(self.coll_pos_selected, self.coll_pos_summary)  # 初始化摘要

        # 最低词频（每千次节点词中搭配词出现的次数）
        minfreq_layout = self._add_row(form_layout, 
                                       self.tr("最低词频"), 
                                       self.tr("过滤过低频搭配（单位：每千次节点词共现）。设为0则表示不过滤。"))
        self.min_freq_spin = QDoubleSpinBox()
        self.min_freq_spin.setRange(0.0, 500.0)
        self.min_freq_spin.setDecimals(1)
        self.min_freq_spin.setSingleStep(0.5)
        self.min_freq_spin.setValue(2.5)
        self.min_freq_spin.setSuffix(" /K")     # 视觉提示：每千次 node_freq
        minfreq_layout.addWidget(self.min_freq_spin)
        
        # 开始按钮
        self.start_btn = QPushButton(self.tr("抽取搭配"))
        self.start_btn.clicked.connect(self.start_task)
        form_layout.addRow(self.start_btn)

        # 【关键】开启KWIC功能：连接双击信号
        if hasattr(self, 'tbl_view'):
            self.tbl_view.itemDoubleClicked.connect(self.on_table_double_click)

    # ---------- 槽函数 ----------
    @Slot()
    def choose_input_file(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 txt 文件"), "", "Text Files (*.txt)")
        if path:
            self.input_edit.setText(path)

    @Slot()
    def choose_input_dir(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("选择目录"), "")
        if d:
            self.input_edit.setText(d)

    @Slot()
    def _choose_pos(self, target: str=""):
        if target=="node":
            title = self.tr("选择节点词性")
            target_set = self.node_pos_selected
            target_edit = self.node_pos_summary
        elif target=="coll":
            title = self.tr("选择搭配词性")
            target_set = self.coll_pos_selected
            target_edit = self.coll_pos_summary
        dlg = MultiSelectDialog(self, title=title, 
                                items=self.POS_TAGS, 
                                preselected=target_set)
        if dlg.exec() == QDialog.Accepted:
            target_set.clear()
            target_set.update(dlg.selected_values())
            self._refresh_pos_summary(target_set, target_edit)

    def _refresh_pos_summary(self, select_set, summary_edit):
        if not select_set:
            summary_edit.setText("")  # 留空，显示占位符“未选择（不限制）”
            return
        # 将 tag 映射回 label，用于摘要展示
        tag2label = {tag: label for (label, tag) in self.POS_TAGS}
        labels = [tag2label.get(t, t) for t in select_set]
        labels.sort()
        text = ",".join(labels)
        summary_edit.setText(text)
        summary_edit.setCursorPosition(0)  # 光标回到开头，便于查看前缀

    # @Slot(QTableWidgetItem)
    @Slot()
    def on_table_double_click(self, item):
        # 1. 获取行号
        row = item.row()
        
        # 2. 从表格获取信息
        # 假设表格列顺序是: Rank, Side, Collocate, POS, Strength, Dist
        # 最好去查 TableViewer 的 header 或者写死索引
        # 注意：这里强依赖表格列的顺序，未来若改动列顺序需同步修改
        side_text = self.tbl_view.item(row, 1).text()  # "Left" or "Right"
        collocate = self.tbl_view.item(row, 2).text()
        pos_text = self.tbl_view.item(row, 3).text()   # e.g. "VERB", "NOUN"
        
        # 3. 获取其他必要信息 (计算后，全部数据已经存储在 Page._data_cache["str"] 中)
        # 尝试解析缓存数据
        if self._data_cache and "str" in self._data_cache:
            try:
                data = json.loads(self._data_cache["str"])
                node_word = data["NODE_WORD"]
                lang = data["LANG"]
                case_sensitive = data["CASE_SENSITIVE"]
                use_lemma = data["USE_LEMMA"]
                win_size = tuple(data["WINDOW_SIZE"])
                    
            except Exception as e:
                print(f"Error parsing cached result: {e}")
                return
            
        else:
            return
                
        input_path = self.input_edit.text() # 注意：这里需要考虑 input_path 之前是不是被清理了，或者是否有效
        
        # 4. 启动搜索 (建议用 Loading 弹窗 + 后台线程，因为搜索可能要几秒)
        # 这里为了演示简单，直接调用（可能会卡顿一下），建议后续封装成 Worker
        self._set_ui_enabled(False)

        self.start_thread(CollocationWorker("KWIC", {
            "src_path": input_path,
            "node_word": node_word,
            "collocate": collocate,
            "side": side_text,
            "coll_pos": pos_text,
            "lang": lang,
            "window_size": win_size,
            "case_sensitive": case_sensitive, 
            "use_lemma": use_lemma
        }))

    @Slot()
    def start_task(self):
        # 参数合法性检查
        lang = self.lang_combo.currentData()
        case_sensitive = self.case_sensitive_chk.isChecked() if lang in ["en", "fr", "de"] else False
        use_lemma = self.use_lemma_chk.isChecked() if lang in ["en", "fr", "de", "ja"] else False

        input_path = self.input_edit.text().strip()
        if not input_path:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先选择语料文件或文件夹。"))
            return
        else:
            if os.path.isfile(input_path) and not input_path.lower().endswith(".txt"):
                QMessageBox.warning(self, self.tr("提示"), self.tr("请选择 .txt 格式的语料文件。"))
                return
            elif os.path.isdir(input_path) and not any(os.scandir(input_path)):
                QMessageBox.warning(self, self.tr("提示"), self.tr("选中的文件夹为空！请重新选择。"))
                return

        node_word = self.node_word_edit.text().strip()
        if not node_word:
            QMessageBox.warning(self, self.tr("提示"), self.tr("节点词不能为空。"))
            return
        node_pos = list(self.node_pos_selected)   # [] 表示不限制
        
        metric = self.metric_combo.currentData()
        window_size = (self.win_left.value(), self.win_right.value()) # QSpinBox / QDoubleSpinBox 永远有值，不用检查用户留空
        coll_pos = list(self.coll_pos_selected)               # [] 表示不限制
        min_freq = float(self.min_freq_spin.value()) / 1000   # 除以单位1000

        # 根据输入信息生成默认输出名
        self._save_default_path = f"FC_{node_word}_{metric}.json"

        # 锁 UI
        self._set_ui_enabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # 启动后台线程
        self.start_thread(CollocationWorker("RETRIEVE", {
            "lang": lang, 
            "case_sensitive": case_sensitive, 
            "use_lemma": use_lemma, 
            "input_path": input_path, 
            "node_word": node_word, 
            "node_pos": node_pos, 
            "metric": metric, 
            "window_size": window_size, 
            "coll_pos": coll_pos, 
            "min_freq": min_freq,
        }))


# =========== 搭配可视化 ===========
class FCVisualPage(PageWidget):
    def __init__(self):
        super().__init__(
            title=self.tr("搭配可视化"),
            hint=self.tr("将已提取的弗思搭配数据进行二维坐标呈现。"),
            view_type=["fig"], 
            save_type="fig"
        )
        # 向 self.form 添加输入组件
        form_layout = QFormLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)

        # 选择输入 -----------------------
        json_layout = self._add_row(form_layout, 
                                    self.tr("搭配数据"), 
                                    self.tr("选择要进行可视化呈现的弗思搭配数据（JSON）。"))
        self.json_edit = self._add_edit_btn(json_layout, 
                                            edit_placeholder="*.json", 
                                            buttons=[
                                                (self.tr("文件"), self.choose_input_json)
                                                ])

        # 横轴范围
        xrange_layout = self._add_row(form_layout, 
                                      self.tr("横轴范围"), 
                                      self.tr("设置横轴（搭配距离）的显示范围。"))
        self.x_left = QSpinBox()
        self.x_left.setRange(0, 5)
        self.x_left.setValue(5)   # 默认值可调
        self.x_right = QSpinBox()
        self.x_right.setRange(0, 5)
        self.x_right.setValue(5)   # 默认值可调
        xrange_layout.addWidget(QLabel(self.tr("左")))
        xrange_layout.addWidget(self.x_left)
        xrange_layout.addSpacing(8)
        xrange_layout.addWidget(QLabel(self.tr("右")))
        xrange_layout.addWidget(self.x_right)
        xrange_layout.addStretch()

        # 纵轴范围
        yrange_layout = self._add_row(form_layout, 
                                      self.tr("纵轴范围"), 
                                      self.tr("设置纵轴（关联强度）的显示范围。"))
        self.y_bottom = QDoubleSpinBox()
        self.y_bottom.setRange(-0.05, 0.95)   # 支持小数范围
        self.y_bottom.setSingleStep(0.05)     # 每次调整步长
        self.y_bottom.setDecimals(2)          # 显示两位小数
        self.y_bottom.setValue(-0.02)         # 默认下限值（可改）
        self.y_top = QDoubleSpinBox()
        self.y_top.setRange(0.05, 1.05)
        self.y_top.setSingleStep(0.05)
        self.y_top.setDecimals(2)
        self.y_top.setValue(1.02)
        yrange_layout.addWidget(QLabel(self.tr("下")))
        yrange_layout.addWidget(self.y_bottom)
        yrange_layout.addSpacing(8)
        yrange_layout.addWidget(QLabel(self.tr("上")))
        yrange_layout.addWidget(self.y_top)
        yrange_layout.addStretch()

        # 添加分隔线
        self._add_split_line(form_layout)

        # 文本字体 -----------------------
        fontfam_layout = self._add_row(form_layout, 
                                       self.tr("绘图字体"), 
                                       self.tr("选择全图所使用的文本字体。列表为检测到系统本地可用的字体，若需扩展更多字体，请前往系统设置进行字体安装。"))
        self.font_family_combo = QComboBox()
        # 添加字体选项
        self.font_family_combo.addItem(self.tr("默认字体(Noto Sans SC)"), userData="")
        for fam, path in CJK_LIST:
            self.font_family_combo.addItem(fam+" (CJK)", userData=fam)  # data 存路径，显示家族名
        for fam, path in LATIN_LIST:
            self.font_family_combo.addItem(fam+" (LATIN)", userData=fam)  # data 存路径，显示家族名
        fontfam_layout.addWidget(self.font_family_combo)

        # 文本字号
        fontsize_layout = self._add_row(form_layout, 
                                        self.tr("绘图字号"), 
                                        self.tr("调整全图所使用的文本字号大小（pt）。"))
        self.fontsize_spin = QDoubleSpinBox()
        self.fontsize_spin.setRange(1.0, 4.0)  # 字号范围，可自行调整
        self.fontsize_spin.setSingleStep(0.5)  # 每次微调步长
        self.fontsize_spin.setDecimals(1)      # 保留1位小数
        self.fontsize_spin.setValue(2.5)       # 默认值
        self.fontsize_spin.setSuffix("pt")    # 显示单位
        fontsize_layout.addWidget(QLabel(self.tr("基本")))
        fontsize_layout.addWidget(self.fontsize_spin)
        self.nodesize_spin = QDoubleSpinBox()
        self.nodesize_spin.setRange(4.0, 8.0)
        self.nodesize_spin.setSingleStep(0.5)
        self.nodesize_spin.setDecimals(1)
        self.nodesize_spin.setValue(6.0)
        self.nodesize_spin.setSuffix("pt")
        fontsize_layout.addWidget(QLabel(self.tr("节点")))
        fontsize_layout.addWidget(self.nodesize_spin)
        fontsize_layout.addStretch()

        # 节点位置（百分比）
        nodepos_layout = self._add_row(form_layout, 
                                       self.tr("节点位置"), 
                                       self.tr("节点词在成图Y方向上的位置（百分比），50%为垂直居中。"))
        self.node_pos_pct = QSpinBox()
        self.node_pos_pct.setRange(0, 100)
        self.node_pos_pct.setValue(30)   # 默认 30%，大约下方 1/3
        self.node_pos_pct.setSuffix("%")
        nodepos_layout.addWidget(self.node_pos_pct)
        nodepos_layout.addStretch()

        # 标点样式 -----------------------
        marker_layout = self._add_row(form_layout, 
                                      self.tr("标点样式"), 
                                      self.tr("设置每个搭配词标记点的透明度及尺寸。"))
        self.marker_alpha = QDoubleSpinBox()
        self.marker_alpha.setRange(0.0, 1.0)
        self.marker_alpha.setSingleStep(0.1)
        self.marker_alpha.setDecimals(1)
        self.marker_alpha.setValue(0.7)
        marker_layout.addWidget(QLabel(self.tr("透明")))
        marker_layout.addWidget(self.marker_alpha)
        self.marker_size = QDoubleSpinBox()
        self.marker_size.setRange(0.10, 0.50)
        self.marker_size.setSingleStep(0.05)
        self.marker_size.setDecimals(2)
        self.marker_size.setValue(0.25)
        marker_layout.addWidget(QLabel(self.tr("大小")))
        marker_layout.addWidget(self.marker_size)
        marker_layout.addStretch()

        # 添加分隔线
        self._add_split_line(form_layout)

        # 拥挤优化 -----------------------
        scheme_layout = self._add_row(form_layout, 
                                      self.tr("拥挤优化"), 
                                      self.tr("当数据量过大，标签文本容易重叠影响阅读，针对此问题可选择采取渲染优化方案。"))
        self.scheme_combo = QComboBox()
        self.scheme_combo.addItems([self.tr("不优化"), self.tr("标签就近错位"), self.tr("标签就远去重")])
        scheme_layout.addWidget(self.scheme_combo)

        # 簇点合并参数面板：右侧一个容器，内部再放一个小表单
        allocate_subform_layout = self._add_subform(
            form_layout, 
            init_vis=False, 
            event_trigger=self.scheme_combo.currentIndexChanged, # 关联到 self.scheme_combo 选项
            show_if=2 # 当 self.scheme_combo 的值变更为2时显示子面板
            )
        # 距离控制
        a_dist_layout = self._add_row(allocate_subform_layout, 
                                      self.tr("距离限制"), 
                                      self.tr("允许标签文本远离点位的距离区间（下限与上限）。"))
        self.allo_dist_min = QDoubleSpinBox()
        self.allo_dist_min.setRange(0.001, 0.02)
        self.allo_dist_min.setDecimals(3)
        self.allo_dist_min.setSingleStep(0.002)
        self.allo_dist_min.setValue(0.003)
        self.allo_dist_max = QDoubleSpinBox()
        self.allo_dist_max.setRange(0.02, 0.5)
        self.allo_dist_max.setDecimals(2)
        self.allo_dist_max.setSingleStep(0.01)
        self.allo_dist_max.setValue(0.4)
        a_dist_layout.addWidget(self.allo_dist_min)
        a_dist_layout.addWidget(QLabel("-"))
        a_dist_layout.addWidget(self.allo_dist_max)
        a_dist_layout.addStretch()

        # 簇点合并选项 -----------------------
        cluster_layout = self._add_row(form_layout, 
                                       self.tr("簇点合并"), 
                                       self.tr("可选。可将位置极其接近的点合并为更大的点，以提升图片的整洁度。被合并点的标签文本也会被连接合一。"))
        self.cluster_chk = QCheckBox(self.tr("进行合并"))
        self.cluster_chk.setChecked(False)
        cluster_layout.addWidget(self.cluster_chk)
        cluster_layout.addStretch()

        # 簇点合并参数面板：右侧一个容器，内部再放一个小表单
        cluster_subform_layout = self._add_subform(
            form_layout, 
            init_vis=False, 
            event_trigger=self.cluster_chk.toggled, # 关联到 self.cluster_chk 选项
            show_if=True # 当 self.cluster_chk 被勾选时显示子面板
            )
        # 合并距离
        m_dist_layout = self._add_row(cluster_subform_layout, 
                                      self.tr("合并距离"), 
                                      self.tr("当两个搭配词之间的距离小于此值时，会被合并为一个更大的点。"))
        self.merge_dist = QDoubleSpinBox()
        self.merge_dist.setRange(0.01, 0.3)
        self.merge_dist.setSingleStep(0.02)
        self.merge_dist.setDecimals(2)
        self.merge_dist.setValue(0.05)
        m_dist_layout.addWidget(self.merge_dist)
        # 标签截取
        m_labeln_layout = self._add_row(cluster_subform_layout, 
                                        self.tr("标签截取"), 
                                        self.tr("搭配词被合并后，标签也会被连接合并。标签过多时，超出此值的标签将被隐藏为+k。"))
        self.label_n_spin = QSpinBox()
        self.label_n_spin.setRange(0, 20)
        self.label_n_spin.setValue(3)
        m_labeln_layout.addWidget(self.label_n_spin)
        # 膨胀倍率
        m_expandr_layout = self._add_row(cluster_subform_layout, 
                                         self.tr("标点放大"), 
                                         self.tr("搭配词被合并后，聚点的膨胀倍率。例如2表示每吸收一个点，聚点的面积便扩大200%。"))
        self.expand_ratio = QDoubleSpinBox()
        self.expand_ratio.setRange(0.0, 5.0)
        self.expand_ratio.setDecimals(1)
        self.expand_ratio.setSingleStep(0.5)
        self.expand_ratio.setValue(1.5)
        m_expandr_layout.addWidget(self.expand_ratio)

        # 开始按钮 -----------------------
        self.start_btn = QPushButton(self.tr("开始制图"))
        self.start_btn.clicked.connect(self.start_task)
        form_layout.addRow(self.start_btn)
    
    # ---------- 槽函数 ----------
    @Slot()
    def choose_input_json(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 json 文件"), "", "JSON Files (*.json)")
        if path:
            self.json_edit.setText(path)

    @Slot()
    def start_task(self):
        # 参数合法性检查
        json_path = self.json_edit.text().strip()
        if not json_path or not os.path.isfile(json_path) or not json_path.lower().endswith(".json"):
            QMessageBox.warning(self, self.tr("提示"), self.tr("请选择 .json 格式的语料文件。"))
            return
        
        # 根据输入文件名生成默认输出名（例如 agatha_p.json → agatha_p.png）
        stem, _ = os.path.splitext(json_path)
        self._save_default_path = f"{stem}.png"
        
        x_range = (self.x_left.value(), self.x_right.value())
        if x_range[0]==0 and x_range[1]==0:
            QMessageBox.warning(self, self.tr("提示"), self.tr("横轴的左右范围不能同时为0！"))
            return
        
        y_range = (self.y_bottom.value(), self.y_top.value())
        if y_range[0] >= y_range[1]:
            QMessageBox.warning(self, self.tr("提示"), self.tr("纵轴范围的下端值不能超过上端值！"))
            return
        
        font_size = self.fontsize_spin.value()
        node_size = self.nodesize_spin.value()
        node_pos_pct = self.node_pos_pct.value()
        font_path = self.font_family_combo.currentData() # 可能是 ""
        marker_alpha = self.marker_alpha.value()
        marker_size = self.marker_size.value()

        # 文本拥挤的优化方案
        scheme_text = self.scheme_combo.currentText()
        scheme_params = None
        # 【重要】逻辑判断也需要加 self.tr，以匹配界面上的翻译值
        if scheme_text == self.tr("不优化"):
            adjust_text_mode = ""
        elif scheme_text == self.tr("标签就近错位"):
            adjust_text_mode = "simple"
        elif scheme_text == self.tr("标签就远去重"):
            adjust_text_mode = "allocate"
            scheme_params = {
                "dist_win": (self.allo_dist_min.value(), self.allo_dist_max.value())
            }

        # 簇点合并选项
        cluster_params = None
        if self.cluster_chk.isChecked():
            cluster_params = {
                "cluster_radio": float(self.merge_dist.value()),
                "label_n": int(self.label_n_spin.value()),
                "expand_ratio": float(self.expand_ratio.value())
            }

        # 锁 UI
        self._set_ui_enabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # 启动后台线程
        self.start_thread(CollocationWorker("VISONLY", {
            "json_path": json_path,
            "x_range": x_range,
            "y_range": y_range,
            "font_size": font_size,
            "node_size": node_size,
            "node_pos_pct": node_pos_pct,      # 节点位置（百分比）
            "font_family": font_path,          # 字体的系统路径
            "marker_alpha": marker_alpha,      # 点透明度
            "marker_size": marker_size,        # 基础点面积
            "adjust_text_mode": adjust_text_mode, # 是否自动调整文本标签位置
            "scheme_params": scheme_params,    # 某些标签拥挤优化方案会附带参数
            "cluster_params": cluster_params,  # 聚合参数选项
        }))


# =========== 相似性计算 ===========
class FCSimilarityPage(PageWidget):
    def __init__(self):
        super().__init__(
            title=self.tr("相似性计算"),
            hint=self.tr("计算两个弗思搭配之间的相似性。"),
            view_type=["tbl", "str"], 
            save_type="str"
        )
        # 向 self.form 添加输入组件
        form_layout = QFormLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)

        # 数据输入栏 -----------------------
        # JSON 文件1，两个按钮：可选文件/目录
        input_layout_1 = self._add_row(form_layout, 
                                       self.tr("数据1"), 
                                       self.tr("选择要进行比较计算的弗思搭配数据（JSON）。"))
        self.json1_edit = self._add_edit_btn(input_layout_1, 
                                             edit_placeholder=self.tr("*.json 或 目录路径"), 
                                             buttons=[
                                                 (self.tr("文件"), self.choose_json1), 
                                                 (self.tr("目录"), self.choose_input_dir1)])

        # JSON 文件2，两个按钮：可选文件/目录
        input_layout_2 = self._add_row(form_layout, 
                                       self.tr("数据2"), 
                                       self.tr("选择要进行比较计算的弗思搭配数据（JSON）。"))
        self.json2_edit = self._add_edit_btn(input_layout_2, 
                                             edit_placeholder=self.tr("*.json 或 目录路径"), 
                                             buttons=[
                                                 (self.tr("文件"), self.choose_json2), 
                                                 (self.tr("目录"), self.choose_input_dir2)])

        # 惩罚系数 -----------------------
        penalty_layout = self._add_row(form_layout, 
                                       self.tr("惩罚系数"), 
                                       self.tr("独有词的惩罚系数。系数越大，独有搭配词对整体相似度影响就越大。若设为0.0则等同于仅比较共有搭配词的相似性。"))
        self.penalty_spin = QDoubleSpinBox()
        self.penalty_spin.setRange(0.00, 1.00)
        self.penalty_spin.setSingleStep(0.05)
        self.penalty_spin.setDecimals(2)
        self.penalty_spin.setValue(0.80)
        penalty_layout.addWidget(self.penalty_spin)
        penalty_layout.addStretch()

        # 汇报选项 -----------------------
        report_layout = self._add_row(form_layout, 
                                      self.tr("汇报选项"), 
                                      self.tr("可选。可选择汇报更多细节，包括共有搭配词、特有搭配词等详细信息。"))
        self.report_chk = QCheckBox(self.tr("汇报细节"))
        self.report_chk.setChecked(False)
        report_layout.addWidget(self.report_chk)
        report_layout.addStretch()

        # 开始按钮
        self.start_btn = QPushButton(self.tr("开始计算"))
        self.start_btn.clicked.connect(self.start_task)
        form_layout.addRow(self.start_btn)

    # ---------- 槽函数 ----------
    @Slot()
    def choose_json1(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 JSON 文件 1"), "", "JSON Files (*.json)")
        if path:
            self.json1_edit.setText(path)
            
    @Slot()
    def choose_input_dir1(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("选择目录 1"), "")
        if d:
            self.json1_edit.setText(d)

    @Slot()
    def choose_json2(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 JSON 文件 2"), "", "JSON Files (*.json)")
        if path:
            self.json2_edit.setText(path)
    
    @Slot()
    def choose_input_dir2(self):
        d = QFileDialog.getExistingDirectory(self, self.tr("选择目录 2"), "")
        if d:
            self.json2_edit.setText(d)

    @Slot()
    def start_task(self):
        # 参数合法性检查
        json_path1 = self.json1_edit.text().strip()
        if not json_path1:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先选择有效的 JSON 数据或文件夹 1。"))
            return
        else:
            if os.path.isfile(json_path1) and not json_path1.lower().endswith(".json"):
                QMessageBox.warning(self, self.tr("提示"), self.tr("请选择 .json 格式的语料文件。"))
                return
            elif os.path.isdir(json_path1) and not any(os.scandir(json_path1)):
                QMessageBox.warning(self, self.tr("提示"), self.tr("选中的文件夹为空！请重新选择。"))
                return
        
        json_path2 = self.json2_edit.text().strip()
        if not json_path2:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先选择有效的 JSON 数据或文件夹 2。"))
            return
        else:
            if os.path.isfile(json_path2) and not json_path2.lower().endswith(".json"):
                QMessageBox.warning(self, self.tr("提示"), self.tr("请选择 .json 格式的语料文件。"))
                return
            elif os.path.isdir(json_path2) and not any(os.scandir(json_path2)):
                QMessageBox.warning(self, self.tr("提示"), self.tr("选中的文件夹为空！请重新选择。"))
                return

        # 根据输入文件名生成默认输出名（例如 agatha_p.json → agatha_p_synsets.json）
        filename1 = os.path.basename(json_path1)     # "example.json"
        stem1, _ = os.path.splitext(filename1)     # ("example", ".json")
        filename2 = os.path.basename(json_path2)
        stem2, _ = os.path.splitext(filename2)
        self._save_default_path = f"{stem1}X{stem2}.json"

        unique_penalty = self.penalty_spin.value()
        report_detail = self.report_chk.isChecked()

        # 锁 UI
        self._set_ui_enabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # 启动后台线程
        self.start_thread(CollocationWorker("SIMILARITY", {
            "json_path_1": json_path1,
            "json_path_2": json_path2,
            "unique_penalty": unique_penalty,
            "report_detail": report_detail
        }))


# =========== 语义抽象 ===========
class FCAbstractionPage(PageWidget):
    def __init__(self):
        super().__init__(
            title=self.tr("语义抽象"),
            hint=self.tr("将搭配词归纳为更抽象的语义单元。不适用德语。"),
            view_type=["tbl", "fig", "str"], 
            save_type="str"
        )
        # 向 self.form 添加输入组件
        form_layout = QFormLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)

        # JSON 文件
        json_layout = self._add_row(form_layout, 
                                    self.tr("搭配数据"), 
                                    self.tr("选择要进行语义抽取的弗思搭配数据（JSON）。"))
        self.json_edit = self._add_edit_btn(json_layout, 
                                            edit_placeholder="*.json",
                                            buttons=[
                                                (self.tr("文件"), self.choose_json)
                                                ])
        
        # 处理侧别 -----------------------
        side_layout = self._add_row(form_layout, 
                                    self.tr("处理侧别"), 
                                    self.tr("可选择对全部搭配词或某一侧搭配词进行语义抽取。"))
        self.side_combo = QComboBox()
        self.side_combo.addItem(self.tr("全部搭配词"), userData="both")
        self.side_combo.addItem(self.tr("左侧搭配词"), userData="left")
        self.side_combo.addItem(self.tr("右侧搭配词"), userData="right")
        side_layout.addWidget(self.side_combo)

        # 词性过滤 -----------------------
        pos_layout = self._add_row(form_layout, 
                                   self.tr("处理词性"), 
                                   self.tr("选择参与语义抽象计算的搭配词词性。"))
        self.cb_verb = QCheckBox(self.tr("动词"))
        self.cb_noun = QCheckBox(self.tr("名词"))
        self.cb_adj = QCheckBox(self.tr("形容词"))
        # 默认全部勾选
        self.cb_verb.setChecked(True)
        self.cb_noun.setChecked(True)
        self.cb_adj.setChecked(True)
        pos_layout.addWidget(self.cb_verb)
        pos_layout.addWidget(self.cb_noun)
        pos_layout.addWidget(self.cb_adj)
        pos_layout.addStretch()
        
        # 开始按钮
        self.start_btn = QPushButton(self.tr("开始抽象"))
        self.start_btn.clicked.connect(self.start_task)
        form_layout.addRow(self.start_btn)

    # ---------- 槽函数 ----------
    @Slot()
    def choose_json(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("选择 JSON 文件"), "", "JSON Files (*.json)")
        if path:
            self.json_edit.setText(path)
    
    @Slot()
    def start_task(self):
        # 参数合法性检查
        json_path = self.json_edit.text().strip()
        if (not json_path) or (not os.path.isfile(json_path)) or (not json_path.lower().endswith(".json")):
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先选择有效的 JSON 文件。"))
            return
        
        # 根据输入文件名生成默认输出名（例如 agatha_p.json → agatha_p_synsets.json）
        stem, _ = os.path.splitext(json_path)
        self._save_default_path = f"{stem}_synsets.json"
        
        side = self.side_combo.currentData() # "both", "left", "right"

        wanted_pos = set()
        if self.cb_noun.isChecked():
            wanted_pos.add("NOUN")
        if self.cb_verb.isChecked():
            wanted_pos.add("VERB")
        if self.cb_adj.isChecked():
            wanted_pos.add("ADJ")
        # 校验：至少选一个
        if not wanted_pos:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请至少选择一种要处理的词性！"))
            return
        
        # 锁 UI
        self._set_ui_enabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # 启动后台线程
        self.start_thread(CollocationWorker("ABSTRACTION", {
            "json_path": json_path,
            "side": side,
            "wanted_pos": wanted_pos
        }))


# ======= 后台任务 Worker（QThread） ========
class CollocationWorker(QObject):
    progress = Signal(int)              # 0~100
    status = Signal(str)                # 状态文本
    finished = Signal(object)           # 返回 Figure 或 数据 或 None
    error = Signal(str)                 # 错误信息（已格式化）

    def __init__(self, task_type: str, task_data: dict):
        super().__init__()
        self.task_type = task_type
        self.task_data = task_data

    @Slot()
    def run(self):
        try:
            # 组装一个统一的“汇聚器”：把 reporter 的上报转成 Qt 信号
            def progress_cb(p: int, msg: str = ""):
                self.progress.emit(p)
                if msg:
                    self.status.emit(msg)
            # 用ProgressReporter包一层，把 root.callback 传给业务函数即可
            reporter = ProgressReporter(progress_cb)  # 默认区间 0..100

            # 调用任务目标函数
            if self.task_type == "RETRIEVE":
                result = self.obtain_collocation(reporter)
            elif self.task_type == "VISONLY":
                result = self.visualize_collocation(reporter)
            elif self.task_type == "SIMILARITY":
                result = self.compute_similarity(reporter)
            elif self.task_type == "ABSTRACTION":
                result = self.get_semantic_abstraction(reporter)
            elif self.task_type == "KWIC":
                result = self.do_kwic_search(reporter)

            # 结果可能是 Figure，也可能是别的结构，这里原样抛回 UI 去判断
            self.progress.emit(100)
            self.finished.emit(result)

        except Exception:
            err = traceback.format_exc()
            self.error.emit(err)

    def obtain_collocation(self, reporter: ProgressReporter):
        # 模型导入、对象建立
        reporter.report(0, self.tr("初始化任务……"))
        ca = CollocationRetriever(
            lang=self.task_data["lang"], 
            metric=self.task_data["metric"],
            winsize=self.task_data["window_size"],
            case_sensitive=self.task_data["case_sensitive"], 
            use_lemma=self.task_data["use_lemma"], 
            min_cofreq_percentage=self.task_data["min_freq"], 
            coll_pos_filter=self.task_data["coll_pos"]
        )

        # 从语料提取搭配数据
        reporter.report(5, self.tr("提取搭配……"))
        fc = ca.obtain_fc_pipeline(
            self.task_data["input_path"], 
            self.task_data["node_word"], 
            node_pos_list=self.task_data["node_pos"], # node.pos: "PROPN", "ADV", "VERB", "NOUN"
            reporter=reporter.child(5, 85) # 下传子区间
        )

        # 1. 生成 JSON 字符串（用于保存功能，及写入 _last_result）
        reporter.report(85, self.tr("整理数据……"))
        json_res = fc.save_to_json()

        # 2. 生成表格数据列表（用于 TableViewer 显示）
        reporter.report(86, self.tr("整理数据……"))
        # 我们需要把 fc 对象里的左/右搭配数据解包并扁平化
        table_data = []

        # 辅助函数：处理单侧数据
        def _process_side(collocates, strengths, positions, poses, side_label):
            tmp_list = []
            # 将四个列表打包在一起
            zipped = list(zip(collocates, strengths, positions, poses))
            # 按强度降序排序
            zipped.sort(key=lambda x: x[1], reverse=True)
            # 遍历生成字典
            for rank, (word, strength, dist, pos) in enumerate(zipped, 1):
                tmp_list.append({
                    "Rank": rank,
                    "Side": side_label,      # 侧别：Left / Right
                    "Collocate": word,       # 搭配词
                    "POS": pos,              # 词性
                    "Strength": strength,    # 强度 (TableViewer会自动保留3位小数)
                    "Distance": dist         # 平均距离
                })
            return tmp_list
        
        # 分别处理左右两侧
        table_data += _process_side(fc.left_collocates, fc.left_strength, fc.left_pstns, fc.left_pos_list, "Left")
        table_data += _process_side(fc.right_collocates, fc.right_strength, fc.right_pstns, fc.right_pos_list, "Right")

        # 3. 生成图片（用于可视化 Tab）
        reporter.report(90, self.tr("绘图中……"))
        fig = fc.visualize_matplotlylib(
            reporter=reporter.child(90, 100) # 下传子区间
        )

        reporter.report(100, self.tr("完成。"))

        # 【关键】同时返回三个结果：
        # 1. json_res (str) -> 会被 PageWidget 存入 _last_result，用于后续保存文件
        # 2. table_data (list) -> 会被自动填充到 TableViewer
        # 3. fig (Figure) -> 会被自动填充到 MplCanvas
        return [json_res, table_data, fig]
    
    def visualize_collocation(self, reporter: ProgressReporter):
        # 建立弗思搭配对象
        reporter.report(0, self.tr("初始化任务……"))
        fc = FirthianCollocation()

        # 导入数据
        reporter.report(5, self.tr("读取数据……"))
        fc.load_from_json(self.task_data["json_path"])

        # 绘图
        reporter.report(30, self.tr("绘图中……"))
        fig = fc.visualize_matplotlylib(
            self.task_data["x_range"], 
            self.task_data["y_range"], 
            text_font_size=self.task_data["font_size"],
            node_size=self.task_data["node_size"],
            node_pos_pct=self.task_data["node_pos_pct"],
            font_family=self.task_data["font_family"],
            marker_alpha=self.task_data["marker_alpha"],
            marker_size=self.task_data["marker_size"],
            adjust_text_mode=self.task_data["adjust_text_mode"], 
            scheme_params=self.task_data["scheme_params"],
            cluster_params=self.task_data["cluster_params"],
            reporter=reporter.child(30, 100) # 下传子区间
        )

        reporter.report(100, self.tr("完成。"))
        return [fig]
    
    def compute_similarity(self, reporter: ProgressReporter):
        # 根据用户设置的路径类型，有三种不同的情况：文件vs文件；文件vs目录；目录vs目录
        path1 = self.task_data["json_path_1"]
        path2 = self.task_data["json_path_2"]
        is_file1 = os.path.isfile(path1)
        is_file2 = os.path.isfile(path2)

        # 辅助函数：收集目录 p 下的所有 .json 路径
        def _collect_json_files(p: str) -> list[str]:
            if os.path.isdir(p):
                files = [os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".json")]
                files.sort()  # 按文件名排序以保证稳定、可复现
                return files
            raise FileNotFoundError(self.tr("路径不存在或不是 .json 文件/目录：") + p)
        
        # 辅助函数：生成表格的一行数据
        def _make_row(p1: str, p2: str, result_dict: str):
            row = {
                "File A": os.path.basename(p1),
                "File B": os.path.basename(p2),
                "Similarity": result_dict.get("OVERALL_SIMILARITY", 0.0)
            }
            # 如果启用了细节汇报，尝试提取左右相似度
            if "LEFT" in result_dict:
                row["L. Sim"] = result_dict["LEFT"].get("SIMILARITY", 0.0)
            if "RIGHT" in result_dict:
                row["R. Sim"] = result_dict["RIGHT"].get("SIMILARITY", 0.0)
            return row
        
        # 初始化结果容器
        json_output = ""
        table_data = []
    
        # ---------------
        # 情况1：文件vs文件
        if is_file1 and is_file2:
            # 建立弗思搭配对象1
            reporter.report(0, self.tr("读取数据……"))
            fc1 = FirthianCollocation(json_path=path1)
            # 建立弗思搭配对象2
            reporter.report(15, self.tr("读取数据……"))
            fc2 = FirthianCollocation(json_path=path2)
            # 计算相似性
            reporter.report(30, self.tr("计算相似性……"))
            json_output = fc1.get_similarity(fc2, 
                                          unique_penalty=self.task_data["unique_penalty"],
                                          report_detail=self.task_data["report_detail"])
            # 解析结果以生成表格
            sim_data = json.loads(json_output)
            table_data.append(_make_row(path1, path2, sim_data))

            reporter.report(100, self.tr("完成。"))
        
        # ---------------
        # 情况2：文件vs目录
        elif is_file1 != is_file2:
            reporter.report(0, self.tr("扫描路径文件……"))
            if is_file1:
                path_sing = path1
                path_list = _collect_json_files(path2)
            else:
                path_sing = path2
                path_list = _collect_json_files(path1)
            # 开始计算
            reporter.report(30, self.tr("读取数据……"))
            fc_sing = FirthianCollocation(json_path=path_sing)
            
            results: list[dict] = []

            for path in reporter.wrap(path_list, 
                                      start=40, end=100, message_each=self.tr("计算相似性……")):
                fc_other = FirthianCollocation(json_path=path)
                sim_data = fc_sing.get_similarity(fc_other, 
                                                  unique_penalty=self.task_data["unique_penalty"],
                                                  report_detail=self.task_data["report_detail"])
                # 1. 添加到 JSON 结构列表
                results.append({
                    "FC_1": path_sing, 
                    "FC_2": path, 
                    "RESULT": json.loads(sim_data)
                })
                # 2. 添加到表格数据列表
                table_data.append(_make_row(path_sing, path, json.loads(sim_data)))
            
            json_output = json.dumps(results, ensure_ascii=False, indent=4)
            reporter.report(100, self.tr("完成。"))
        
        # ---------------
        # 情况3：目录vs目录
        elif not is_file1 and not is_file2:
            # 按顺序一一对应；数量不等时，多出来的忽略
            reporter.report(0, self.tr("扫描路径文件……"))
            list1 = _collect_json_files(path1)
            list2 = _collect_json_files(path2)
            total_pairs = min(len(list1), len(list2))

            results: list[dict] = []

            reporter.report(30, self.tr("配对计算相似性……"))
            for i in reporter.wrap(range(total_pairs), 
                                      start=30, end=100, message_each=self.tr("配对计算相似性……")):
                fc1 = FirthianCollocation(json_path=list1[i])
                fc2 = FirthianCollocation(json_path=list2[i])
                sim_data = fc1.get_similarity(fc2, 
                                              unique_penalty=self.task_data["unique_penalty"],
                                              report_detail=self.task_data["report_detail"])
                # 1. 添加到 JSON 结构列表
                results.append({
                    "FC_1": list1[i], 
                    "FC_2": list2[i], 
                    "RESULT": json.loads(sim_data)
                })
                # 2. 添加到表格数据列表
                table_data.append(_make_row(list1[i], list2[i], json.loads(sim_data)))

            json_output = json.dumps(results, ensure_ascii=False, indent=4)
            reporter.report(100, self.tr("完成。"))
        
        else:
            return ["ERROR: Input paths should either be a JSON file or directory that contains JSON files."]
        
        return [json_output, table_data]

    def get_semantic_abstraction(self, reporter: ProgressReporter):
        # 建立弗思搭配对象
        reporter.report(0, self.tr("读取数据……"))
        fc = FirthianCollocation(json_path=self.task_data["json_path"])

        # 进行搭配抽取
        reporter.report(15, self.tr("进行语义抽取……"))
        try:
            # 1. 获取 JSON 字符串结果
            json_res = fc.semantic_abstraction(
                side=self.task_data["side"], 
                wanted_pos=self.task_data["wanted_pos"], 
                reporter=reporter.child(15,100)
            )

            # 2. 解析数据以供表格和绘图使用
            res_dict = json.loads(json_res)
            
            table_data = []

            # 1. 处理有层级的 (Abstracted Concepts)
            for item in res_dict.get("HYPERNYMS", []):
                table_data.append({
                    "Type": "hypernym",
                    "Synset": item["synset"],
                    "Score": item["score"],
                    "Source Words": item.get("source_words", "")
                })
            
            # 2. 处理无层级的 (Direct Concepts)
            for item in res_dict.get("DIRECTS", []):
                table_data.append({
                    "Type": "direct",
                    "Synset": item["synset"],
                    "Score": item["score"],
                    "Source Words": item.get("source_words", "")
                })

            # 按分数重新排序（虽然内部排过了，但合并后可能乱序，这里简单按分数统排一次）
            table_data.sort(key=lambda x: x["Score"], reverse=True)

            # 3. 生成可视化图表
            reporter.report(95, self.tr("绘图中……"))
            fig = fc.visualize_abstraction(res_dict, top_n=15) # 显示前15个概念

            reporter.report(100, self.tr("完成。"))
            return [json_res, table_data, fig]
        
        except Exception as e:
            # 出错时返回错误文本，UI 会弹窗提示
            return [str(e)]
    
    def do_kwic_search(self, reporter):
        # 实例化轻量级搜索器
        searcher = ConcordanceSearcher(
            lang=self.task_data["lang"],
            case_sensitive=self.task_data["case_sensitive"],
            use_lemma=self.task_data["use_lemma"]
        )
        
        # 执行搜索
        results = searcher.search(
            src_path=self.task_data["src_path"],
            node_word=self.task_data["node_word"],
            collocate_word=self.task_data["collocate"],
            window_size=self.task_data["window_size"],
            side = self.task_data["side"], 
            coll_pos = self.task_data["coll_pos"],
            reporter=reporter
        )

        return [{"type": "kwic_result", 
                 "data": results, 
                 "node": self.task_data["node_word"], 
                 "coll": self.task_data["collocate"]}]