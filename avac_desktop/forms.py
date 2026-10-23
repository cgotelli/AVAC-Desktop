"""Small contextual editors bound to one complete scientific configuration."""
from __future__ import annotations

from .i18n import tr, trf, tr_list, number, parse_number
from copy import deepcopy
from typing import Any

import yaml
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLayout, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QStackedLayout, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from avac_desktop.core.configuration import controlled_values, default_limiter_for_model, validate_controlled_values, normalize_mesh_configuration, mesh_sizes
from .project import ProjectSession


def muted(text: str) -> QLabel:
    label = QLabel(tr(text))
    label.setObjectName("Muted")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class CurrentPageLayout(QStackedLayout):
    """Inactive long forms must not create scrollbars on a short active page."""
    def minimumSize(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page else QSize(0, 0)

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else QSize(0, 0)

    def hasHeightForWidth(self):
        page = self.currentWidget()
        return bool(page and page.layout() and page.layout().hasHeightForWidth())

    def heightForWidth(self, width):
        page = self.currentWidget()
        return page.layout().heightForWidth(width) if page and page.layout() else -1

    def minimumHeightForWidth(self, width):
        return self.heightForWidth(width)


class ConfigurationPanels(QWidget):
    changed = Signal()
    problem = Signal(str)

    def __init__(self, session: ProjectSession, parent=None):
        super().__init__(parent)
        self.stack = CurrentPageLayout(self)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.layout().setSizeConstraint(QLayout.SetNoConstraint)
        self.session = session
        self.controls: dict[str, QWidget] = {}
        self.pages: dict[str, QWidget] = {}
        self.layouts: dict[str, QVBoxLayout] = {}
        for key, title in (("terrain", "Terrain & release"), ("release", "Release conditions"),
                           ("material", "Material & rheology"), ("numerics", "Numerical settings"),
                           ("run", "Run"), ("wave", "Waves"), ("analyze", "Map"),
                           ("profiles", "Profiles"), ("gauges", "Gauges")):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setSizeConstraint(QLayout.SetNoConstraint)
            layout.setContentsMargins(16, 16, 16, 16)
            label = QLabel(tr(title))
            label.setObjectName("Title")
            layout.addWidget(label)
            if key in ("release", "material", "numerics", "run"):
                notice = muted("No parameters loaded. Use File → Load standard parameters or Load AVAC configuration.")
                notice.setObjectName("EmptyParameters")
                layout.addWidget(notice)
            self.pages[key], self.layouts[key] = page, layout
            self.addWidget(page)
        self.terrain_info = muted("Import a projected terrain DEM to begin.")
        self.layouts["terrain"].addWidget(self.terrain_info)
        self.release_info = muted("Import release polygons to define mobile snow.")
        self.layouts["release"].addWidget(self.release_info)
        self._build_release()
        self._build_material()
        self._build_numerics()
        self.run_info = muted("Validate inputs, inspect an initial-state preview, then prepare a new isolated run.")
        self.layouts["run"].addWidget(self.run_info)
        self.wave_info = muted("WAVE consumes a completed AVAC run read only and writes a separate scenario. Water level is an absolute DEM elevation.")
        self.wave_info.setParent(self.pages["wave"])
        self.wave_info.hide()
        self._build_wave()
        self.analysis_info = muted("Open a project to restore its completed results. Terrain is available in both modes.")
        self.analysis_info.setParent(self.pages["analyze"])
        self.analysis_info.hide()
        for layout in self.layouts.values():
            layout.addStretch()
        self.refresh()

    def minimumSizeHint(self):
        # The scroll area's viewport defines the panel width. Inactive pages
        # must not force the current form beyond that viewport at high DPI.
        page = self.currentWidget()
        height = page.layout().minimumSize().height() if page and page.layout() else 0
        if page and page.layout() and page.layout().hasHeightForWidth():
            height = max(height, page.layout().heightForWidth(max(280, self.width())))
        return QSize(280, height)

    def sizeHint(self):
        return self.minimumSizeHint()

    def addWidget(self, widget):
        return self.stack.addWidget(widget)

    def currentWidget(self):
        return self.stack.currentWidget()

    def setCurrentWidget(self, widget):
        self.stack.setCurrentWidget(widget)
        self.updateGeometry()

    def group(self, page: str, title: str) -> QFormLayout:
        box = QGroupBox(tr(title))
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.layouts[page].addWidget(box)
        return form

    def number(self, form: QFormLayout, label: str, path: str, low: float, high: float,
               *, decimals: int = 5, integer: bool = False, hint: str = "") -> QWidget:
        spin = QSpinBox() if integer else QDoubleSpinBox()
        spin.setRange(int(low) if integer else low, int(high) if integer else high)
        if not integer:
            spin.setDecimals(decimals)
            spin.setSingleStep(.1)
        spin.setKeyboardTracking(False)
        spin.setToolTip(tr(hint) if hint else trf('{0} — stored in the full AVAC configuration; checked by scientific preflight.', tr(label)))
        spin.valueChanged.connect(lambda value, p=path: self.set_value(p, value))
        form.addRow(tr(label), spin)
        self.controls[path] = spin
        return spin

    def check(self, form, label, path):
        check = QCheckBox(tr(label))
        check.toggled.connect(lambda value, p=path: self.set_value(p, value))
        form.addRow(tr(check))
        self.controls[path] = check

    def set_value(self, path: str, value: Any) -> None:
        group, key = path.split(".", 1)
        self.session.configuration.setdefault(group, {})[key] = value
        if path == "computation.t_max":
            self._timing_changed()
        if path in ("computation.cell_size", "computation.refinement"):
            self.refresh()
        self.session.dirty = True
        self.changed.emit()

    def _build_release(self):
        form = self.group("release", "Mobile release")
        self.number(form, "Base depth d₀ [m]", "release.d0", 0, 1000)
        self.number(form, "Return period [years]", "release.period_return", 1, 100000, integer=True,
                    hint="Scenario metadata only; does not change the physical equations.")
        self.check(form, "Apply slope correction", "release.correction_slope")
        self.number(form, "Critical slope [°]", "release.theta_cr", -90, 90)
        self.number(form, "Slope factor ν", "release.nu", -100, 100)
        self.check(form, "Apply elevation correction", "release.correction_elevation")
        self.number(form, "Reference elevation [m]", "release.z_ref", -10000, 10000)
        self.number(form, "Hypsometric gradient", "release.gradient_hypso", -100, 100,
                    hint="Existing AVAC correction uses gradient_hypso × (elevation − z_ref) / 100.")

    def _build_wave(self):
        form = self.group("wave", "Initial lake coupling")
        self.wave_controls = {"duration": self.wave_duration}
        for key, title, low, high, decimals in (
            ("water_level", "Absolute water level [m]", -10000, 10000, 4),
            ("damping", "Snow-to-water damping", 0, .4, 4),
            ("land_strickler", "Land Strickler [m⅓/s]", .0001, 1000, 4),
            ("water_strickler", "Water Strickler [m⅓/s]", .0001, 1000, 4),
            ("friction_depth_limit", "Friction depth limit [m]", .0001, 10000, 4),
            ("dry_limit", "Dry-depth limit [m]", .000001, 1, 6),
            ):
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setDecimals(decimals)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(lambda value, k=key: self._wave_changed(k, value))
            form.addRow(tr(title), spin)
            self.wave_controls[key] = spin

    def _wave_changed(self, key, value):
        self.session.wave_setup[key] = value
        if key == "duration":
            self._timing_changed()
            return
        self.session.dirty = True
        self.changed.emit()

    def _build_material(self):
        form = self.group("material", "Constitutive law")
        self.model = QComboBox()
        for label, value in (("Coulomb", "Coulomb"), ("Voellmy", "Voellmy"), ("Cohesive Voellmy", "cohesive_Voellmy")):
            self.model.addItem(tr(label), value)
        self.model.activated.connect(self._model_selected)
        form.addRow(tr("Model"), self.model)
        self.controls["rheology.model"] = self.model
        self.number(form, "Bulk density [kg/m³]", "rheology.rho", .001, 10000)
        self.layouts["material"].addWidget(muted("Elevation zones retain their inactive ξ and C values when the physical model changes."))
        self.zones = QTableWidget(0, 4)
        from .number_widgets import NumericDelegate
        self.zones.setItemDelegate(NumericDelegate(self.zones))
        self.zones.setHorizontalHeaderLabels(tr_list(["Lower z [m]", "μ", "ξ [m/s²]", "C [Pa]"]))
        self.zones.horizontalHeader().setStretchLastSection(True)
        self.zones.setMinimumHeight(170)
        self.zones.setColumnWidth(0, 82)
        self.zones.setColumnWidth(1, 58)
        self.zones.setColumnWidth(2, 84)
        self.layouts["material"].addWidget(self.zones)
        row = QHBoxLayout()
        self.zone_buttons = []
        for title, callback in (("Add zone", self._add_zone), ("Remove zone", self._remove_zone), ("Apply zones", self._apply_zones)):
            button = QPushButton(tr(title))
            button.clicked.connect(callback)
            row.addWidget(button)
            self.zone_buttons.append(button)
        self.layouts["material"].addLayout(row)

    def _model_selected(self):
        model = self.model.currentData()
        self.set_value("rheology.model", model)
        self.set_value("computation.limiter", default_limiter_for_model(model))
        self.refresh()

    def _add_zone(self):
        row = self.zones.rowCount()
        self.zones.insertRow(row)
        from .number_widgets import numeric_item
        for col, value in enumerate([1500, .25, 1100, 0]):
            self.zones.setItem(row, col, numeric_item(value))

    def _remove_zone(self):
        if self.zones.rowCount() > 1:
            self.zones.removeRow(max(1, self.zones.currentRow()))

    def _apply_zones(self):
        try:
            result = deepcopy(self.session.configuration)
            rows = [[float(self.zones.item(r, c).data(Qt.EditRole)) for c in (1, 2, 3)] for r in range(self.zones.rowCount())]
            breaks = [float(self.zones.item(r, 0).data(Qt.EditRole)) for r in range(1, len(rows))]
            import numpy as np
            if not np.all(np.isfinite(np.asarray(rows))) or not np.all(np.isfinite(breaks)):
                raise ValueError("Zone values must be finite.")
            for i, key in enumerate(("mu", "xi", "C")):
                values = [row[i] for row in rows]
                result["rheology"][key] = values if len(rows) > 1 else values[0]
            result["rheology"]["z_breaks"] = breaks
            issues = validate_controlled_values(controlled_values(result))
            if issues:
                raise ValueError("\n".join(issues))
            self.session.configuration = result
            self.session.dirty = True
            self.changed.emit()
        except (ValueError, AttributeError, TypeError) as exc:
            self.problem.emit(str(exc))

    def _build_numerics(self):
        form = self.group("run", "Time parameters")
        self.number(form, "Avalanche duration [s]", "computation.t_max", .0001, 1e7)
        self.wave_duration = QDoubleSpinBox()
        self.wave_duration.setRange(.0001, 1e7)
        self.wave_duration.setDecimals(5)
        self.wave_duration.setKeyboardTracking(False)
        self.wave_duration.valueChanged.connect(lambda value: self._wave_changed("duration", value))
        self.wave_duration_label = QLabel(tr("Wave duration [s]"))
        form.addRow(tr(self.wave_duration_label), self.wave_duration)
        self.output_interval = QDoubleSpinBox()
        self.output_interval.setRange(.000001, 1e7)
        self.output_interval.setDecimals(6)
        self.output_interval.setKeyboardTracking(False)
        form.addRow(tr("Time between outputs [s]"), self.output_interval)
        self.output_interval.valueChanged.connect(self._timing_changed)
        self.timing_info = muted("")
        form.addRow(tr(self.timing_info))
        self.timing_error = ""
        form = self.group("numerics", "Mesh")
        self.number(form, "Smallest cell size [m]", "computation.cell_size", .000001, 10000, decimals=6)
        self.number(form, "AVAC AMR levels", "computation.refinement", 1, 8, integer=True)
        self.number(form, "AMR update interval [s]", "computation.regrid_seconds", .01, 10000, decimals=2,
                    hint="Simulated time between AVAC mesh updates. One level uses a uniform grid.")
        self.mesh_info = muted("")
        form.addRow(tr(self.mesh_info))
        self.wave_mesh_info = muted("")
        self.layouts["wave"].addWidget(self.wave_mesh_info)
        form2 = self.group("numerics", "Numerical method")
        self.number(form2, "CFL target", "computation.cfl_target", .0001, 1)
        self.number(form2, "CFL maximum", "computation.cfl_max", .0001, 1)
        self.number(form2, "Max-result check Δt [s]", "output.delta_t", .0001, 1000000)
        limiter = QComboBox()
        limiter.addItems(tr_list(["none", "minmod", "superbee", "mc", "vanleer"]))
        limiter.currentTextChanged.connect(lambda value: self.set_value("computation.limiter", value))
        self.controls["computation.limiter"] = limiter
        form2.addRow(tr("Limiter"), limiter)
        self.layouts["numerics"].addWidget(muted("Outer boundaries: extrapolating. Native output: binary32. Advanced values remain in the complete YAML."))

    def refresh(self):
        self.session.configuration = normalize_mesh_configuration(self.session.configuration)
        configured = bool(self.session.configuration)
        if configured:
            finest, base, levels = mesh_sizes(self.session.configuration)
            self.mesh_info.setText(trf('AVAC: {0:g} m base → {1:g} m finest; ratio 1:2 between levels.', base, finest))
            self.wave_mesh_info.setText(trf('WAVE: uniform {0:g} m cells.', finest))
        else:
            self.mesh_info.clear()
            self.wave_mesh_info.clear()
        if configured and self.session.wave_setup.get("duration") is None:
            self.session.wave_setup["duration"] = float(self.session.configuration["computation"]["t_max"])
        self.wave_duration.setVisible(self.session.wave_enabled)
        self.wave_duration_label.setVisible(self.session.wave_enabled)
        for notice in self.findChildren(QLabel, "EmptyParameters"):
            notice.setVisible(not configured)
        for key, widget in self.wave_controls.items():
            widget.blockSignals(True)
            widget.setEnabled(configured)
            if configured:
                widget.setValue(self.session.wave_setup[key])
            else:
                widget.clear()
            widget.blockSignals(False)
        for path, widget in self.controls.items():
            group, key = path.split(".", 1)
            value = self.session.configuration.get(group, {}).get(key)
            widget.blockSignals(True)
            widget.setEnabled(value is not None)
            if value is None:
                if isinstance(widget, QCheckBox):
                    widget.setChecked(False)
                elif isinstance(widget, QComboBox):
                    widget.setCurrentIndex(-1)
                else:
                    widget.clear()
                widget.blockSignals(False)
                continue
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                index = widget.findData(value) if widget is self.model else widget.findText(str(value))
                if index < 0:
                    widget.addItem(tr(str(value).replace("_", " ")), value)
                    index = widget.count()-1
                widget.setCurrentIndex(index)
            else:
                if value < widget.minimum():
                    widget.setMinimum(value)
                if value > widget.maximum():
                    widget.setMaximum(value)
                widget.setValue(value)
            widget.blockSignals(False)
        self.controls["computation.regrid_seconds"].setEnabled(configured and levels > 1)
        self._refresh_timing()
        material = self.session.configuration.get("rheology", {})
        self.zones.setEnabled(configured)
        for button in self.zone_buttons:
            button.setEnabled(configured)
        if not material:
            self.zones.setRowCount(0)
            return
        values = [material.get(key, 0) for key in ("mu", "xi", "C")]
        values = [v if isinstance(v, list) else [v] for v in values]
        self.zones.setRowCount(len(values[0]))
        breaks = material.get("z_breaks", [])
        for row in range(len(values[0])):
            from .number_widgets import numeric_item
            lower = QTableWidgetItem(tr("All lower z")) if row == 0 else numeric_item(breaks[row-1])
            self.zones.setItem(row, 0, lower)
            if row == 0:
                self.zones.item(row, 0).setFlags(Qt.ItemIsEnabled)
            for col in range(3):
                self.zones.setItem(row, col+1, numeric_item(values[col][row]))
                relevant = col == 0 or (col == 1 and material.get("model") != "Coulomb") or (col == 2 and material.get("model") == "cohesive_Voellmy")
                if not relevant:
                    self.zones.item(row, col+1).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def show_page(self, key: str):
        self.setCurrentWidget(self.pages[key])
        self.updateGeometry()

    def _refresh_timing(self):
        config = self.session.configuration
        self.output_interval.blockSignals(True)
        self.output_interval.setEnabled(bool(config))
        self.timing_error = ""
        if config:
            duration = float(config["computation"]["t_max"])
            count = max(1, int(config["animation"]["n_out"])-1)
            self.output_interval.setValue(duration/count)
            self.timing_info.setText(trf('{0} intervals · {1} frames, including initial and final states.', count, count+1))
            if int(config["computation"]["nb_simul"]) != count:
                self.timing_info.setText(tr("Imported configuration has separate native/temporal schedules. Editing duration or interval will synchronize them."))
            self._wave_timing_info(duration/count)
        else:
            self.output_interval.clear()
            self.timing_info.clear()
        self.output_interval.blockSignals(False)

    def _timing_changed(self, *_):
        from .preferences import set_output_interval
        try:
            count = set_output_interval(self.session.configuration, self.output_interval.value())
            self.timing_error = ""
            self.timing_info.setText(trf('{0} intervals · {1} frames, including initial and final states.', count, count+1))
            self._wave_timing_info(self.output_interval.value())
        except (ValueError, KeyError) as exc:
            self.timing_error = str(exc)
            self.timing_info.setText(tr(self.timing_error))
        self.session.dirty = True
        self.changed.emit()

    def _wave_timing_info(self, interval):
        if not self.session.wave_enabled:
            return
        from .preferences import output_count
        try:
            count = output_count(float(self.session.wave_setup["duration"]), interval)
            self.timing_info.setText(tr(self.timing_info.text()+trf('\nWAVE: {0} intervals · {1} frames.', count, count+1)))
        except (ValueError, TypeError) as exc:
            self.timing_error = "WAVE: "+str(exc)
            self.timing_info.setText(tr(self.timing_error))
