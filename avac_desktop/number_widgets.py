"""Locale-aware presentation with numeric model data, never localized storage."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QStyledItemDelegate, QTableWidgetItem
import pyqtgraph as pg
from .i18n import number, numeric_locale


def numeric_item(value):
    item = QTableWidgetItem()
    item.setData(Qt.EditRole, float(value))
    return item


class NumericDelegate(QStyledItemDelegate):
    def displayText(self, value, locale):
        return number(value, '.12g') if isinstance(value, (int, float)) else str(value)

    def createEditor(self, parent, option, index):
        editor = QDoubleSpinBox(parent)
        editor.setLocale(numeric_locale())
        editor.setDecimals(12)
        editor.setRange(-1e15, 1e15)
        editor.setKeyboardTracking(False)
        return editor

    def setEditorData(self, editor, index):
        editor.setValue(float(index.data(Qt.EditRole)))

    def setModelData(self, editor, model, index):
        editor.interpretText()
        model.setData(index, editor.value(), Qt.EditRole)


class NumericAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        texts = super().tickStrings(values, scale, spacing)
        if numeric_locale().decimalPoint() == ',':
            return [text.replace('.', ',') for text in texts]
        return texts
