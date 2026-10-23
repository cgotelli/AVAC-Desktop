"""Display-only colour ramps and raster style editor."""
from .i18n import tr, trf, tr_list, number, parse_number
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QLabel, QSpinBox)

PALETTES = {
    "Terrain": ["#354e49", "#6b7e64", "#a29e7a", "#b9b49d", "#e4e8e3"],
    "Ocean to fire": ["#1e5fa8", "#16b9cf", "#83dc97", "#fad050", "#f05e36"],
    "Viridis": ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
    "Blue–red": ["#2767b5", "#d8e1e4", "#e7763c"],
    "Grayscale": ["#20242a", "#f5f7fa"],
}


class RasterStyleDialog(QDialog):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setWindowTitle(tr("Raster appearance"))
        form = QFormLayout(self)
        self.layer = QComboBox()
        self.layer.addItem(tr("Terrain"), "terrain")
        if view.field_raster is not None:
            self.layer.addItem(tr(view.field_label), view.field_label)
        for label in view.additional_fields:
            self.layer.addItem(tr(label), label)
        form.addRow(tr("Layer"), self.layer)
        self.palette = QComboBox()
        for key in PALETTES:
            self.palette.addItem(tr(key), key)
        form.addRow(tr("Palette"), self.palette)
        self.automatic = QCheckBox(tr("Use data range"))
        form.addRow(tr(self.automatic))
        self.low, self.high = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.low, self.high):
            spin.setRange(-1e15, 1e15)
            spin.setDecimals(8)
        form.addRow(tr("Minimum"), self.low)
        form.addRow(tr("Maximum"), self.high)
        self.zero = QCheckBox(tr("Exactly zero is transparent"))
        form.addRow(tr(self.zero))
        self.legend = QCheckBox(tr("Show this layer's legend"))
        form.addRow(tr(self.legend))
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(tr(" %"))
        form.addRow(tr("Layer opacity"), self.opacity)
        self.error = QLabel()
        self.error.setWordWrap(True)
        form.addRow(tr(self.error))
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttons.rejected.connect(self.reject)
        form.addRow(tr(buttons))
        self.automatic.toggled.connect(lambda checked: (self.low.setEnabled(not checked), self.high.setEnabled(not checked)))
        self.layer.currentIndexChanged.connect(self.load)
        self.load()

    def load(self):
        key = self.layer.currentData()
        style = self.view.styles.get(key, {})
        self.palette.setCurrentIndex(self.palette.findData(style.get("palette", self.view.default_palette(key))))
        low, high = self.view.range_for(key)
        limits = style.get("limits")
        self.automatic.setChecked(limits is None)
        self.low.setValue(limits[0] if limits else low)
        self.high.setValue(limits[1] if limits else high)
        self.low.setEnabled(limits is not None)
        self.high.setEnabled(limits is not None)
        self.zero.setChecked(style.get("zero_transparent", self.view.default_zero_transparent(key)))
        self.legend.setChecked(style.get("legend_visible", True))
        self.opacity.setValue(round(style.get("opacity", 1.)*100))

    def apply(self):
        if not self.automatic.isChecked() and self.high.value() <= self.low.value():
            self.error.setText(tr("Maximum must be greater than minimum."))
            return
        self.view.styles[self.layer.currentData()] = dict(palette=self.palette.currentData(),
            limits=None if self.automatic.isChecked() else [self.low.value(), self.high.value()],
            zero_transparent=self.zero.isChecked(), opacity=self.opacity.value()/100, legend_visible=self.legend.isChecked())
        self.view.refresh_styles()
        self.view.styles_changed.emit()
        self.error.setText(tr("Applied. Scientific raster values are unchanged."))
