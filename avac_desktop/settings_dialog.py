"""Appearance and per-field scientific defaults for future projects."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)
import yaml
from .forms import ConfigurationPanels, muted
from .preferences import appearance, default_configuration, default_wave_setup, save_defaults
from .project import ProjectSession


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(840, 760)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Appearance"))
        self.appearance = QComboBox()
        self.appearance.addItem("Light", "light")
        self.appearance.addItem("Dark", "dark")
        self.appearance.setCurrentIndex(self.appearance.findData(appearance()))
        row.addWidget(self.appearance)
        row.addStretch()
        root.addLayout(row)
        root.addWidget(muted("Defaults apply to new projects. Existing project parameters are preserved. Appearance changes immediately after saving settings."))
        row = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.addItems(["Release conditions", "Material & rheology", "Numerics", "Run timing", "WAVE", "Advanced YAML"])
        self.navigation.addItem("Online backgrounds")
        self.navigation.setUniformItemSizes(True)
        self.navigation.setMinimumWidth(200)
        for index in range(self.navigation.count()):
            self.navigation.item(index).setSizeHint(QSize(180, 42))
        row.addWidget(self.navigation, 1)
        self.session = ProjectSession(configuration=default_configuration(), wave_setup=default_wave_setup(), wave_enabled=True)
        self.panels = ConfigurationPanels(self.session)
        self.panels.release_info.setText("Default mobile release parameters for new projects.")
        self.advanced = QPlainTextEdit()
        self.panels.addWidget(self.advanced)
        from .basemap import PROVIDERS
        from .preferences import settings
        self.network_page = QWidget()
        form = QFormLayout(self.network_page)
        form.addRow(muted("Backgrounds are optional. The provider receives requests for visible map tiles; terrain and release files are not uploaded. No offline-area download is provided. Set a compatible HTTPS tile endpoint using {z}, {x}, {y}."))
        self.tile_urls = {}
        for provider, title in (("osm", "OpenStreetMap URL"), ("satellite", "Satellite URL")):
            field = QLineEdit(settings().value(f"tiles/{provider}", PROVIDERS[provider][0]))
            self.tile_urls[provider] = field
            form.addRow(title, field)
        form.addRow(muted("Provider credits remain visible on the map. Use endpoints whose terms allow your intended use."))
        self.panels.addWidget(self.network_page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.panels)
        row.addWidget(scroll, 3)
        root.addLayout(row, 1)
        self.error = muted("")
        root.addWidget(self.error)
        self.panels.problem.connect(self.error.setText)
        self.navigation.currentRowChanged.connect(self.navigate)
        self._last = -1
        self.navigation.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def navigate(self, row):
        if self._last == 5:
            try:
                from avac_desktop.core.configuration import controlled_values, validate_controlled_values
                payload = yaml.safe_load(self.advanced.toPlainText())
                issues = validate_controlled_values(controlled_values(payload))
                if issues:
                    raise ValueError("\n".join(issues))
                self.session.configuration = payload
                self.panels.refresh()
            except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
                self.error.setText(str(exc))
                self.navigation.blockSignals(True)
                self.navigation.setCurrentRow(5)
                self.navigation.blockSignals(False)
                return
        self._last = row
        if row == 6:
            self.panels.setCurrentWidget(self.network_page)
        elif row == 5:
            self.advanced.setPlainText(yaml.safe_dump(self.session.configuration, sort_keys=False))
            self.panels.setCurrentWidget(self.advanced)
        else:
            self.panels.show_page(["release", "material", "numerics", "run", "wave"][row])

    def accept(self):
        try:
            if self._last == 5:
                self.session.configuration = yaml.safe_load(self.advanced.toPlainText())
            if self.panels.timing_error:
                raise ValueError(self.panels.timing_error)
            import math
            for key, value in self.session.wave_setup.items():
                if key != "limiter" and not math.isfinite(float(value)):
                    raise ValueError(f"WAVE {key} must be finite.")
            from PySide6.QtCore import QUrl
            for field in self.tile_urls.values():
                value = field.text().strip()
                url = QUrl(value)
                if url.scheme() != "https" or not url.host() or any(token not in value for token in ("{x}", "{y}", "{z}")):
                    raise ValueError("Tile endpoints must use HTTPS and include {z}, {x}, {y}.")
            save_defaults(self.session.configuration, self.appearance.currentData(), self.session.wave_setup)
            from .preferences import settings
            for provider, field in self.tile_urls.items():
                settings().setValue(f"tiles/{provider}", field.text().strip())
            settings().sync()
            super().accept()
        except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
            self.error.setText(str(exc))
