# ui_page.py
# -*- coding: utf-8 -*-
import os
import csv, openpyxl
from typing import Optional

from PySide6.QtCore import (
    Qt, QObject, QThread, Slot,
    QRect, QSize, Signal
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, 
    QPushButton, QLabel, QPlainTextEdit, QFormLayout, QFrame, 
    QFileDialog, QMessageBox, QSplitter, QSizePolicy, 
    QProgressBar, QStyleOptionProgressBar, QStyle, 
    # for multiSelectDialog
    QDialog, QListWidget, QListWidgetItem, 
    QLineEdit, QDialogButtonBox,
    # for tabular view
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, 
    QStyledItemDelegate, QApplication, # KWICViewer special
)
from PySide6.QtGui import (
    QTextOption, QTextCursor, 
    QPainter, QFontMetrics, 
    QFont,
    QTextDocument
)
from typing import Tuple, Callable

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure



# ============== UI Page基础类 ==============
class PageWidget(QWidget):
    def __init__(self, title="", hint="", view_type=["str"], subview_type=None, save_type="fig"):
        """
        view_type (list): 本页的结果主视图类型，可取值包括 ["fig" (图片), "str" (文本), "tbl" (表格)]。决定的是右侧的显示面板内容。
        subview_type (str | list | None): 本页的结果子视图类型，例如 "kwic"。若不为空，右侧将分割为上下两部分。
        save_type (str): 本页的保存结果类型，可取 fig (图片), str (文本), or None，决定的是左下角按钮及其导出功能。
        """
        super().__init__()

        # 线程成员
        self._thread: Optional[QThread] = None
        self._worker: Optional[QObject] = None

        # 通用属性
        self._save_default_path = ""
        self._data_cache = {}  # 用于分类存储不同类型的结果 (text/table)

        # 统一布局：左交互区、右结果区
        outer = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter)
        
        # 左侧：交互区 ---------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        # 添加标题和小字
        if title:
            title_lbl = QLabel(title)
            title_lbl.setWordWrap(True) # 开启换行
            title_lbl.setProperty("class", "title")
            left_layout.addWidget(title_lbl)
        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True) # 开启换行
            hint_lbl.setProperty("class", "hint")
            left_layout.addWidget(hint_lbl)

        # 创建输入表单
        self.form = QWidget()
        self.form.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.form)
        
        # 留白
        left_layout.addStretch()

        # 创建进度条
        self.progress = LabelProgressBar()
        # self.progress.setRange(0, 100)
        # self.progress.setValue(0)
        self.progress.setVisible(False)
        left_layout.addWidget(self.progress)

        # 创建导出按钮
        if save_type == "fig":
            self.save_btn = QPushButton(self.tr("保存图片"))
            self.save_btn.clicked.connect(self.save_figure)
            self.save_btn.setEnabled(False)
        elif save_type == "str":
            self.save_btn = QPushButton(self.tr("保存结果"))
            self.save_btn.clicked.connect(self.save_result)
            self.save_btn.setEnabled(False)
        else:
            self.save_btn = None

        if self.save_btn:
            left_layout.addWidget(self.save_btn)

        # 右侧：结果区 ---------------
        # right = QWidget()
        # right_layout = QVBoxLayout(right)
        # right_layout.setContentsMargins(12, 12, 12, 12)
        # 支持主视图 + 可选子视图
        right_splitter = QSplitter(Qt.Vertical)

        # 输出窗口（结果呈现的载体，有三种格式类型）
        self.tbl_view = None
        self.fig_view = None
        self.str_view = None
        self.kwic_view = None # 新增引用

        # 1. 创建主视图区域
        main_view_widget = self._create_view_widget(view_type, placeholder=self.tr("结果将在这里显示。"))
        right_splitter.addWidget(main_view_widget)

        # output_area = self._create_output_area(view_type, placeholder=self.tr("结果将在这里显示。"))
        # if output_area:
        #     right_layout.addWidget(output_area)
        # else:
        #     print("警告：有 PageWidget 没有初始化正确的输出类型！")

        # 2. 创建子视图区域 (如果有)
        if subview_type:
            # 统一转列表
            if isinstance(subview_type, str): subview_type = [subview_type]
            
            sub_view_widget = self._create_view_widget(subview_type, placeholder=self.tr("详细信息/KWIC将在这里显示。"))
            right_splitter.addWidget(sub_view_widget)
            
            # 设置初始比例：主视图占 2/3，子视图占 1/3
            right_splitter.setStretchFactor(0, 2)
            right_splitter.setStretchFactor(1, 1)
            right_splitter.setSizes([2000, 1000]) # 强制设置初始高度比例
            right_splitter.setCollapsible(0, False) # 主视图不可被完全折叠
            right_splitter.setCollapsible(1, True)  # 子视图可以被折叠

        # 页面整体布局
        splitter.addWidget(left) # -> left 的索引为 0
        left.setMaximumWidth(340)  # 限制左侧最大宽度，防止长文本无限挤压右侧
        # splitter.addWidget(right) # -> right 的索引为 1
        splitter.addWidget(right_splitter) # 右侧放 Splitter

        splitter.setStretchFactor(0, 0) # -> 索引0 (left) 拉伸因子为 0，即不主动扩展/不参与拉伸
        splitter.setStretchFactor(1, 1) # -> 索引1 (right) 拉伸因子为 1，即占剩余空间
        splitter.setSizes([340, 840])  # 设置初始宽度（左固定宽度，右侧灵活可变）

    # 通用组件和样式相关函数 ----------
    def _create_view_widget(self, types: list, placeholder: str =""):
        """
        types: 列表，可取 ["tbl", "fig", "str"]。 据元素数量创建 独占控件(n=1) 或 TabWidget(n>1)。
        """
        # 辅助函数：根据类型字符串创建具体控件
        def _create_widget(type):
            if type == "str":
                output_edit = QPlainTextEdit()
                output_edit.setReadOnly(True)  # 禁止编辑
                # 允许选择与复制：下面两项确保键鼠可选中
                output_edit.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
                )
                output_edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere) # 合理换行
                output_edit.setPlaceholderText(placeholder)
                return output_edit
            elif type == "fig":
                fig = Figure()
                ax = fig.add_subplot(111)
                ax.text(0.5, 0.5, placeholder, ha="center", va="center")
                ax.set_axis_off()
                return MplCanvas(fig)
            elif type == "tbl":
                return TableViewer()
            elif t == "kwic": # 新增 KWIC 类型
                return KWICViewer()
            return QWidget()
            
        # 1. 如果只有一个元素，创建独占控件 (保持向后兼容)
        if len(types) == 1:
            t = types[0]
            w = _create_widget(t)
            # 【关键】建立引用，方便 on_task_finished 调用
            if t == "tbl": self.tbl_view = w
            if t == "fig": self.fig_view = w
            if t == "str": self.str_view = w 
            if t == "kwic": self.kwic_view = w 
            return w
        
        # 2. 如果有多个元素，创建 TabWidget
        tabs = QTabWidget()
        for t in types:
            w = _create_widget(t)
            if t == "tbl":
                tabs.addTab(w, self.tr("数据列表"))
                self.tbl_view = w
            elif t == "fig":
                tabs.addTab(w, self.tr("可视化图"))
                self.fig_view = w
            elif t == "str":
                tabs.addTab(w, self.tr("文本数据"))
                self.str_view = w
            elif t == "kwic":
                tabs.addTab(w, self.tr("KWIC"))
                self.kwic_view = w
        return tabs

    def _add_row(self, form_layout: QFormLayout, label: str ="", tooltip: str =""):
        """创造一个表格行。返回该行的layout对象，可供添加具体组件。"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        # 设置标签和悬停提示
        if label:
            lbl = QLabel(label)
            lbl.setWordWrap(True)  # 开启自动换行
            if tooltip:
                lbl.setToolTip(tooltip)
            form_layout.addRow(lbl, row)
        else:
            form_layout.addRow(row)
        return row_layout
    
    def _add_subform(self, parent_layout: QFormLayout, init_vis: bool=False, event_trigger: Signal=None, show_if: bool|int|str|list|set|tuple=None):
        """
        封装子表单区域的创建，及事件绑定（用于关联到某一选项的变更信号下）。
        :param parent_layout: QFormLayout 或其他父布局。
        :param init_vis: 初始是否显示。
        :param event_trigger: 使表单可见的触发源，可选的Qt信号对象（如 combo.currentIndexChanged）。目前支持三类触发源：
            - QComboBox 的 currentIndexChanged:int 和 currentTextChanged:str
            - QCheckBox 和 QRadioButton 的 toggled:bool
        :param show_if: 用于绑定显示本subform的信号值，请结合event_trigger进行设定。支持：
            - 单值：当信号值等于该值时显示
            - 列表/集合/元组：当信号值在容器内时显示
        :return: 返回子表单的 QFormLayout 可供添加组件。
        """
        sub_panel = QWidget()
        sub_form = QFormLayout(sub_panel)
        sub_form.setContentsMargins(0, 0, 0, 0)
        sub_form.setLabelAlignment(Qt.AlignLeft)

        # 将子表单加入父布局，标签默认留空
        parent_layout.addRow("", sub_panel)

        # 设定初始显隐 → 整行设置（含左侧的空标签）
        sub_panel.setVisible(init_vis)
        lbl = parent_layout.labelForField(sub_panel)
        if lbl:
            lbl.setVisible(init_vis)

        # 若传入触发信号，则绑定显/隐逻辑
        if event_trigger is not None:
            @Slot()
            def toggle_visibility(value: bool|int|str):
                """
                根据触发信号类型自动切换子表单显隐。
                """
                if isinstance(show_if, (list, set, tuple)):
                    # 信号为 落在多值列表中，显示
                    show = (value in show_if)
                else:
                    # 信号为单值 bool/int/str，仅当 信号值value==预设的show_if 时显示
                    show = (value == show_if)

                sub_panel.setVisible(show)
                lbl = parent_layout.labelForField(sub_panel)
                if lbl:
                    lbl.setVisible(show)

            event_trigger.connect(toggle_visibility)
            # 立刻按默认语言刷新一次可见性
            # toggle_visibility()

        return sub_form

    def _add_split_line(self, parent_layout):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        parent_layout.addRow(line)
        return line

    def _add_edit_btn(self, parent_layout, edit_placeholder: str="", buttons: list[str, Callable]=[]):
        """创建只读 QLineEdit，并在其右侧依次加入若干按钮。
        buttons: 形如 [("选择文件", self.pick_file), ("清空", self.clear_edit)]
        """
        # 摘要框（只读）
        edit = QLineEdit()
        edit.setReadOnly(True)
        if edit_placeholder:
            edit.setPlaceholderText(edit_placeholder)
        parent_layout.addWidget(edit, 1)
        # 按钮
        for btn_text, clicked_action in buttons:
            btn = QPushButton(btn_text)
            btn.clicked.connect(clicked_action)
            parent_layout.addWidget(btn, 0) # 伸缩因子为0（保持最小）
        return edit

    def _set_ui_enabled(self, enabled: bool):
        # 禁用交互表单
        self.form.setEnabled(enabled)
        # 保存按钮：仅关闭时被统一控制
        if self.save_btn and not enabled:
            self.save_btn.setEnabled(False)
    
    # 通用交互函数 ----------
    @Slot()
    def save_result(self):
        """根据 _data_cache 中的内容，智能提供保存选项（JSON/CSV/XLSX/TXT）。"""
        if not self._data_cache:
            QMessageBox.information(self, self.tr("提示"), self.tr("暂无可保存的结果。"))
            return

        # 1. 动态构建文件过滤器
        filters = []
        has_str = "str" in self._data_cache
        has_tbl = "tbl" in self._data_cache
        # 文本类：提供 JSON, TXT 选项
        if has_str:
            filters.append("JSON 数据 (*.json)")
            filters.append("纯文本文件 (*.txt)")
        # 表格类：提供 CSV, XLSX 选项
        if has_tbl:
            filters.append("CSV 表格 (*.csv)")
            filters.append("Excel 工作簿 (*.xlsx)")
        filter_str = ";;".join(filters)

        # 默认保存路径就是刚才生成的 _save_default_path
        default_path = self._save_default_path or "result"

        # 2. 弹出保存对话框
        path, selected_filter = QFileDialog.getSaveFileName(self, self.tr("保存结果"), default_path, filter_str)
        if not path:
            return

        # 3. 确定保存模式 (根据用户选的过滤器或文件后缀)，并自动补全后缀
        mode = "unknown"
        path_lower = path.lower()
        # 判断是否是表格 (xlsx 或 csv)
        if "excel" in selected_filter.lower() or path_lower.endswith(".xlsx"):
            mode = "tbl"
            save_format = "xlsx" # <--- 标记具体格式
            if not path_lower.endswith(".xlsx"): path += ".xlsx"
        elif "csv" in selected_filter.lower() or path_lower.endswith(".csv"):
            mode = "tbl"
            save_format = "csv"
            if not path_lower.endswith(".csv"): path += ".csv"
        # 判断是否是文本 (json 或 txt)
        elif "json" in selected_filter.lower() or path_lower.endswith(".json"):
            mode = "str"
            if not path_lower.endswith(".json"): path += ".json"
        elif "txt" in selected_filter.lower() or path_lower.endswith(".txt"):
            mode = "str"
            if not path_lower.endswith(".txt"): path += ".txt"
        
        # 4. 执行写入
        try:
            content = self._data_cache.get(mode, None)

            # === 保存表格数据 (CSV / XLSX) ===
            if mode == "tbl":
                if not has_tbl:
                    raise ValueError(self.tr("当前没有此类型数据可供保存。"))
                if not content:
                    raise ValueError(self.tr("表格数据为空。")) # 防止取表头报错

                # Branch 1: 保存为 XLSX (Excel)
                if save_format == "xlsx":
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    # 写表头
                    headers = list(content[0].keys())
                    ws.append(headers)
                    # 写数据
                    for row_data in content:
                        # 确保按表头顺序写入 values
                        ws.append([row_data.get(h, "") for h in headers])
                    wb.save(path)
                
                # Branch 2: 保存为 CSV
                else:
                    # 使用 utf-8-sig 编码，确保 Excel 打开中文不乱码
                    with open(path, "w", encoding="utf-8-sig", newline="") as f:
                        # 获取表头 (基于第一行数据的 keys)
                        headers = list(content[0].keys())
                        writer = csv.DictWriter(f, fieldnames=headers)
                        writer.writeheader()
                        writer.writerows(content)
            
            # === 保存 文本/JSON ===
            elif mode == "str":
                if not has_str:
                    raise ValueError(self.tr("当前没有此类型数据可供保存。"))
                
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

            QMessageBox.information(self, self.tr("保存成功"), self.tr("结果已保存到：") + path)

        except Exception as e:
            QMessageBox.critical(self, self.tr("保存失败"), self.tr("错误：") + str(e))

    @Slot()
    def save_figure(self):
        """保存 self.fig_view 中的内容为图片。"""
        if not self.fig_view or self.fig_view.figure is None:
            QMessageBox.information(self, self.tr("提示"), self.tr("当前没有可保存的图像。"))
            return

        # 选择保存路径 & 格式
        default_path = self._save_default_path or "result"
        path, selected_filter = QFileDialog.getSaveFileName(self, self.tr("保存图片"), default_path, "PNG (*.png);;SVG (*.svg)")
        if not path:
            return

        # 根据扩展名/所选过滤器补全后缀
        if "." not in os.path.basename(path):
            if "PNG" in selected_filter: path += ".png"
            elif "SVG" in selected_filter: path += ".svg"
            else: path += ".png"  # 兜底

        try:
            # 保存：推荐用 figure.savefig
            self.fig_view.figure.savefig(path, dpi=600, bbox_inches="tight") # 默认导出最高分辨率600
            QMessageBox.information(self, self.tr("保存成功"), self.tr("图片已保存到：") + path)
        except Exception as e:
            QMessageBox.critical(self, self.tr("保存失败"), self.tr("错误：") + str(e))
    
    def start_thread(self, worker: QObject):
        # 启动后台线程
        self._thread = QThread()
        self._worker = worker
        self._worker.moveToThread(self._thread)

        # 信号连接
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.setValue)    # 更新百分比
        self._worker.status.connect(self.progress.setStatusText) # 更新左侧文本
        self._worker.finished.connect(self.on_task_finished)
        self._worker.error.connect(self.on_task_error)

        # 线程收尾
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()
    
    # 通用回调函数 ----------
    @Slot(str)
    def on_task_error(self, err_text: str):
        self._set_ui_enabled(True)
        if self.progress:
            self.progress.setVisible(False)
        QMessageBox.critical(self, self.tr("运行出错"), self.tr("发生异常：") + err_text)

    @Slot(object)
    def on_task_finished(self, results):
        """
        results接受所有结果内容的列表。
        仅支持两种类型的返回结果：Figure or str。其余类型会以警告弹窗形式显示结果。
        """
        # 解锁 UI
        self._set_ui_enabled(True)
        # self.progress.setVisible(False)
        
        for item in results:
            # 根据 result 的类型执行不同的结果渲染操作
            if isinstance(item, Figure):
                # Case 1: 图片类型
                if self.fig_view:
                    # 更新画布
                    self.fig_view.update_figure(item)

            # Case 2: 文本类型
            elif isinstance(item, str):
                if self.str_view:
                    # 将内容填充到输出框里
                    self.str_view.clear()
                    self.str_view.setPlainText(item)
                    self.str_view.moveCursor(QTextCursor.Start)

                # 缓存结果以供导出
                self._data_cache["str"] = item

            # Case 3: 表格类型
            elif isinstance(item, list):
                if self.tbl_view:
                    # 填充表格
                    self.tbl_view.set_data(item)
                
                # 保存一份 raw data 方便后续保存为 CSV/JSON
                self._data_cache["tbl"] = item

            # Case 4: KWIC类型 (填充到子视图)
            elif isinstance(item, dict) and item.get("type") == "kwic_result":
                # 弹出 KWIC 窗口
                data = item["data"]
                # 检查子视图是否存在
                if self.kwic_view:
                    if not data:
                        # 可以选择清空或者显示“未找到”
                        self.kwic_view.set_data([])
                        QMessageBox.information(self, "KWIC", "未在原语料中找到符合当前窗口范围的例句。")
                    else:
                        self.kwic_view.set_data(data)

            # 其余格式
            else:
                QMessageBox.warning(self, self.tr("任务完成"), repr(item))
        
        # 启用保存结果按钮
        if self.save_btn:
            self.save_btn.setEnabled(True)


# ============== Matplotlib 画布控件 ==============
class MplCanvas(FigureCanvas):
    def __init__(self, fig: Figure | None = None):
        fig = fig or Figure()
        super().__init__(fig)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()

    def update_figure(self, new_fig: Figure):
        """原地更新 Figure，并强制适配当前窗口大小"""
        # 1. 绑定新 Figure
        self.figure = new_fig
        new_fig.set_canvas(self)

        # 2. 【关键步骤】显式同步尺寸
        # 获取当前 Canvas 控件在屏幕上的实际像素宽高
        w = self.width()
        h = self.height()

        # 只有当控件已经显示且有尺寸时才调整
        if w > 0 and h > 0:
            # Matplotlib 的 set_size_inches 接受的是英寸
            # 公式：英寸 = 像素 / DPI
            dpi = new_fig.get_dpi()
            new_fig.set_size_inches(w / dpi, h / dpi)

        # 3. 重绘
        self.draw()


# ============== 表格显示组件 ==============
class TableViewer(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True) # 隔行变色
        self.setEditTriggers(QTableWidget.NoEditTriggers) # 禁止编辑
        self.setSelectionBehavior(QTableWidget.SelectRows) # 选中整行
        # 开启内置排序功能
        self.setSortingEnabled(True)
        # 优化表头显示
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive) # 可调节列宽
        header.setStretchLastSection(True)  # 最后一列宽度弹性设置
        header.setSortIndicatorShown(True)  # 显示排序箭头
        header.setSectionsClickable(True)   # 允许表头点击

    def set_data(self, data_list: list[dict], column_ratios: list[float] = None):
        """
        接收一个字典列表，自动生成表头和内容。
        :param data_list: 数据列表，Example: [{"Rank": 1, "Word": "apple"}, {"Rank": 2, "Word": "banana"}]
        :param column_ratios: (可选) 列宽比例列表，例如 [2, 2, 3, 4]。长度必须与列数一致。
        """
        if not data_list:
            self.clear()
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        # 在填充数据前先关闭排序，否则大数据量时会因为反复重排导致卡顿
        self.setSortingEnabled(False)

        # 1. 设置表头 (基于第一行数据的Keys)
        headers = list(data_list[0].keys())
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)

        # 2. 填充数据
        self.setRowCount(len(data_list))
        for row_idx, row_data in enumerate(data_list):
            for col_idx, key in enumerate(headers):
                val = row_data.get(key, "")

                item = QTableWidgetItem()
                
                if isinstance(val, (int, float)):
                    # 数字
                    # 使用 setData 并传入 Qt.EditRole 存储原始数值（按数值大小排序）
                    item.setData(Qt.EditRole, val)
                    # 对于浮点数：强制界面显示 4 位小数
                    if isinstance(val, float):
                        item.setText(f"{val:.4f}")
                    # 右对齐
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    # 字符串
                    item.setText(str(val))
                
                self.setItem(row_idx, col_idx, item)
        
        # 3. 设置列宽比例 (新增逻辑)
        if column_ratios and len(column_ratios) == len(headers):
            # 获取当前表格视口的宽度
            total_width = self.viewport().width()
            
            # 如果表格还没渲染出来（width为0），给一个默认参考宽度，保证比例正确即可
            if total_width <= 0:
                total_width = 1000 
            
            # 减去滚动条的大致宽度（防止出现横向滚动条），可选
            total_width -= 20 

            total_ratio = sum(column_ratios)
            if total_ratio > 0:
                for col_idx, ratio in enumerate(column_ratios):
                    # 计算像素宽度: (当前列比例 / 总比例) * 总宽度
                    width = int((ratio / total_ratio) * total_width)
                    # 设置列宽
                    self.setColumnWidth(col_idx, width)

        # 数据填充完毕，重新开启排序
        self.setSortingEnabled(True)


# ============== KWIC 专用显示组件 ==============
class HTMLDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        options = option
        self.initStyleOption(options, index)

        painter.save()

        # 1. 准备文档对象
        doc = QTextDocument()
        # 设置 HTML 内容
        doc.setHtml(options.text) 
        
        # 2. 绘制背景 (选中状态高亮、鼠标悬停等)
        style = options.widget.style() if options.widget else QApplication.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, options, painter, options.widget)

        # 3. 调整绘制区域，留出一点 padding
        # rect = options.rect.adjusted(2, 0, -2, 0)
        rect = options.rect.adjusted(0, 0, 0, 0)
        painter.translate(rect.topLeft())
        
        # 4. 设置文档宽度（不要设为 rect.width()，否则会被强制换行。）
        doc.setTextWidth(-1) # 不自动换行
        doc.setDefaultFont(options.font)

        # 5. 处理对齐 (Left Context 需要右对齐)
        # QTextDocument 默认左对齐。如果需要右对齐，需要计算宽度差
        doc_height = doc.size().height()
        # 垂直居中
        y_offset = (rect.height() - doc_height) / 2
        
        # 6. 计算水平对齐偏移
        display_align = index.data(Qt.TextAlignmentRole)
        if display_align is None:
            display_align = Qt.AlignLeft
            
        x_offset = 0
        text_width = doc.idealWidth() # 获取渲染后的实际文本宽度
        if display_align & Qt.AlignRight:
            # 右对齐：内容靠右，左侧超出部分被剪裁（视觉上实现左侧省略）
            x_offset = rect.width() - text_width
        elif display_align & Qt.AlignHCenter:
            # 居中
            text_width = doc.idealWidth()
            x_offset = (rect.width() - text_width) / 2

        # 应用位移
        painter.translate(x_offset, y_offset)
        
        # 剪裁区域（防止画出格子）
        # painter.setClipRect(QRectF(0, 0, rect.width() - x_offset, rect.height()))
        
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        # 告诉表格这一行需要多高（可选）
        return super().sizeHint(option, index)


class KWICViewer(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Left Context", "Node", "Right Context"])
        # KWIC 经典布局：左侧右对齐，中间居中，右侧左对齐
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # 左侧拉伸
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents) # 中间适应内容
        header.setSectionResizeMode(2, QHeaderView.Stretch) # 右侧拉伸
        
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(False) # 去掉网格线
        self.setAlternatingRowColors(True)

        # 给 Left(0) 和 Right(2) 列应用自定义的 HTML 代理
        html_delegate = HTMLDelegate(self)
        self.setItemDelegateForColumn(0, html_delegate) # 左侧上下文
        self.setItemDelegateForColumn(2, html_delegate) # 右侧上下文
    
    def set_data(self, data_list: list[dict]):
        """
        data_list: [{"pre": "...", "key": "...", "post": "..."}, ...]
        """
        self.setRowCount(0) # 清空
        if not data_list: return
        
        self.setRowCount(len(data_list))
        font = self.font()
        
        for i, item in enumerate(data_list):
            pre_txt = item.get("pre", "")
            key_txt = item.get("key", "")
            post_txt = item.get("post", "")

            # Left Context
            it_pre = QTableWidgetItem(pre_txt)
            it_pre.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter) # 右对齐
            self.setItem(i, 0, it_pre)
            
            # Key (高亮)
            it_key = QTableWidgetItem(key_txt)
            it_key.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            it_key.setForeground(Qt.blue)
            bold_font = QFont(font)
            bold_font.setBold(True)
            it_key.setFont(bold_font)
            self.setItem(i, 1, it_key)
            
            # Post (需要高亮里面的搭配词，这里稍微复杂点，V1先简单显示文本)
            it_post = QTableWidgetItem(post_txt)
            it_post.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.setItem(i, 2, it_post)


# ============== 自定义进度条 ==============
class LabelProgressBar(QProgressBar):
    """在同一行进度条上：左侧显示状态文本，右侧显示百分比"""
    # 可选：对外暴露一个更新状态文本的信号，便于跨线程使用
    updateText = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._left_text = ""
        self.setTextVisible(False)     # 关闭原生文字，改为自绘
        self.setRange(0, 100)
        self.setValue(0)               # 初始进度为0
        self.updateText.connect(self.setStatusText)

    @Slot(str)
    def setStatusText(self, txt: str):
        self._left_text = txt or ""
        self.update()

    def setStatus(self, txt: str):
        """非信号方式的直接设置"""
        self._left_text = txt or ""
        self.update()

    def sizeHint(self) -> QSize:
        # 让进度条默认宽一点
        sh = super().sizeHint()
        return QSize(max(sh.width(), 260), max(sh.height(), 18))

    def paintEvent(self, event):
        # 1) 让样式系统先正常绘制进度条
        opt = QStyleOptionProgressBar()
        self.initStyleOption(opt)
        # 我们自绘文字，所以告诉样式不绘制其文字
        opt.textVisible = False

        p = QPainter(self)
        self.style().drawControl(QStyle.CE_ProgressBar, opt, p, self)

        # 2) 计算文本区域并绘制左右文字
        rect = self.rect().adjusted(6, 0, -6, 0)  # 左右留点内边距
        fm = QFontMetrics(self.font())

        # 右侧百分比字符串
        val = self.value()
        right_text = f"{val}%" if self.minimum() < self.maximum() else ""
        right_w = fm.horizontalAdvance(right_text)

        # 右侧对齐的绘制区域
        right_rect = QRect(rect.right() - right_w, rect.top(), right_w, rect.height())

        # 左侧文本：为右侧留出空间，并做省略
        gap = 8
        left_available_w = max(0, rect.width() - right_w - gap)
        left_rect = QRect(rect.left(), rect.top(), left_available_w, rect.height())
        left_text = fm.elidedText(self._left_text, Qt.TextElideMode.ElideRight, left_available_w)

        # 颜色跟随当前调色板（dark / light 都合适）
        pen = self.palette().color(self.foregroundRole())
        p.setPen(pen)

        # 垂直居中对齐
        p.drawText(left_rect, Qt.AlignVCenter | Qt.AlignLeft, left_text)
        p.drawText(right_rect, Qt.AlignVCenter | Qt.AlignRight, right_text)
        p.end()


# ============== 自定义多选弹窗 ==============
class MultiSelectDialog(QDialog):
    def __init__(self, parent=None, title=None, items=None, preselected=None):
        """
        :param items: [(label, value), ...]
        :param preselected: set(values)
        """
        super().__init__(parent)

        title = title or self.tr("选择项")
        self.setWindowTitle(title)

        self.resize(420, 520)
        self.items = items or []
        self.preselected = set(preselected or [])

        vbox = QVBoxLayout(self)

        # 搜索框
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("搜索（支持标签文本）"))
        search_row.addWidget(QLabel(self.tr("筛选")))
        search_row.addWidget(self.search_edit)
        vbox.addLayout(search_row)

        # 列表（带勾选）
        self.listw = QListWidget()
        self.listw.setAlternatingRowColors(True)
        vbox.addWidget(self.listw)

        # 批量操作
        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton(self.tr("全选"))
        self.btn_clear_all  = QPushButton(self.tr("全不选"))
        self.btn_inv        = QPushButton(self.tr("反选"))
        btn_row.addStretch()
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_clear_all)
        btn_row.addWidget(self.btn_inv)
        vbox.addLayout(btn_row)

        # 确定 / 取消
        self.btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        vbox.addWidget(self.btn_box)

        # 数据填充
        self._populate()

        # 连接信号
        self.search_edit.textChanged.connect(self._apply_filter)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_clear_all.clicked.connect(self._clear_all)
        self.btn_inv.clicked.connect(self._invert_selection)
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)

        # 样式统一控制
        self.setAttribute(Qt.WA_StyledBackground, True) # 让样式表绘制顶层背景（mac很重要）

    def _populate(self):
        self.listw.clear()
        for label, value in self.items:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, value)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if value in self.preselected else Qt.Unchecked)
            self.listw.addItem(it)

    def _apply_filter(self, text):
        text = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            visible = (text in it.text().lower()) if text else True
            it.setHidden(not visible)

    def _select_all(self):
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Checked)

    def _clear_all(self):
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Unchecked)

    def _invert_selection(self):
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if not it.isHidden():
                it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)

    def selected_values(self):
        vals = []
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if it.checkState() == Qt.Checked:
                vals.append(it.data(Qt.UserRole))
        return vals

