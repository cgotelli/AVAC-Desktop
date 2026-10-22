"""Persistent main window; contextual panels change, project/map/job do not."""
from __future__ import annotations

from copy import copy, deepcopy
import json
import os
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMenuBar, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)
import pyqtgraph as pg
import yaml

from avac_desktop.core.configuration import load_complete_configuration
from avac_desktop.core.preprocessing import AvacRaster, initial_snow_surface_elevation
from avac_desktop.core.profiles import extract_profile, write_profile_csv
from avac_desktop.core.runtime_assets import default_template_path
from .runtime import ensure_runtime
from avac_desktop.core.runtime import validate_runtime

from .analysis import LABELS, Results, export_geotiff, write_gauge
from .execution import NativeJob
from .forms import ConfigurationPanels, muted
from .geo import read_terrain, read_polygons, sha256_file, has_geographic_reference
from .map_view import MapView, terrain_display
from .project import ProjectSession, load_project, save_project
from . import simulation, workflow
from .workers import Tasks
from .window_chrome import TitleBar, windows_resize_hit
from .preferences import default_configuration, default_wave_setup


class MainWindow(QMainWindow):
    data_loaded = Signal()

    def __init__(self, session: ProjectSession | None = None):
        super().__init__()
        self.session = session or ProjectSession(configuration=default_configuration(), wave_setup=default_wave_setup())
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        from .app import resource_root
        self.setWindowIcon(QIcon(str(resource_root()/"avac_desktop"/"resources"/"AVAC_app_icon.png")))
        self.setWindowTitle("AVAC Desktop")
        self.resize(1500, 950)
        self.setMinimumSize(1050, 700)
        self.tasks = Tasks(self)
        self.tasks.error.connect(self._task_error)
        self.tasks.interaction_busy_changed.connect(self._busy)
        self.tasks.busy_changed.connect(self._task_finished)
        self.job = NativeJob(self)
        self.job.log.connect(self._append_log)
        self.job.state_changed.connect(self._job_state)
        self.job.progress.connect(self._job_progress)
        self.job.completed.connect(self._run_completed)
        self.results: Results | None = None
        self.current_raster: AvacRaster | None = None
        self.current_variable = "terrain_elevation"
        self.current_time = None
        self.profile = None
        self.gauge = None
        self._dataset_identity = ""
        self._result_sources = {}
        self._lake_rings = []
        self._video_export = None
        self._pending_initial_mesh = False
        self._initial_mesh = None
        self._initial_mesh_run = None
        self._pending_frame = False
        self._run_plan = None
        self._pipeline_active = False
        self._pipeline_snapshot = None
        self._action_generation = 0
        self._build()
        self._menus()
        self._sync_dataset_selector()
        self.set_mode(self.session.mode)
        self._update_project()

    def _build(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("Header")
        row = QHBoxLayout(header)
        row.setContentsMargins(22, 14, 22, 14)
        brand = QLabel("AVAC <span style='color:#56bdf2'>Desktop</span>")
        brand.setObjectName("Brand")
        row.addWidget(brand)
        row.addSpacing(28)
        row.addStretch()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.model_button = QPushButton("Model && Run")
        self.analyze_button = QPushButton("Results")
        for button, mode in ((self.model_button, "model_run"), (self.analyze_button, "analyze")):
            button.setCheckable(True)
            button.setMinimumWidth(130)
            button.setMinimumHeight(37)
            button.clicked.connect(lambda checked, m=mode: self.set_mode(m))
            self.mode_group.addButton(button)
            row.addWidget(button)
        layout.addWidget(header)

        self.horizontal = QSplitter(Qt.Horizontal)
        left = QFrame()
        left.setObjectName("Sidebar")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 18, 6, 12)
        self.workflow_label = QLabel("  MODEL WORKFLOW")
        self.workflow_label.setObjectName("Eyebrow")
        left_layout.addWidget(self.workflow_label)
        self.navigation = QListWidget()
        self.navigation.currentRowChanged.connect(self._navigate)
        left_layout.addWidget(self.navigation)
        left_layout.addWidget(muted("  Layers"))
        self.terrain_check = QCheckBox("Terrain")
        self.release_check = QCheckBox("Release polygons")
        self.terrain_check.setChecked(True)
        self.release_check.setChecked(True)
        self.terrain_check.toggled.connect(lambda value: self._layer("terrain", value))
        self.release_check.toggled.connect(lambda value: self._layer("release", value))
        left_layout.addWidget(self.terrain_check)
        left_layout.addWidget(self.release_check)
        self.layer_checks = {"terrain": self.terrain_check, "release": self.release_check}
        for key, title in (("lake", "Lake polygon"), ("mesh", "Initial mesh"), ("profiles", "Profiles"), ("gauges", "Gauges"),
                           ("legends", "Legends"), ("scale", "Scale bar"), ("north", "North arrow")):
            check = QCheckBox(title)
            check.setChecked(self.session.layers.get(key, key != "mesh"))
            if key == "mesh":
                check.setToolTip("Inspect the actual initial AVAC mesh after Prepare, before Run. "
                                 "AMR levels use different colours; zoom in for cells. "
                                 "Available only in Preparation & Run.")
            check.toggled.connect(lambda value, k=key: self._layer(k, value))
            left_layout.addWidget(check)
            self.layer_checks[key] = check
        self.layer_checks["lake"].setVisible(self.session.lake_path is not None)
        for key, kind in (("profiles", "profile"), ("gauges", "gauge")):
            self.layer_checks[key].setVisible(any(f["kind"] == kind for f in self.session.analysis_features))
        left.setMinimumWidth(180)
        self.horizontal.addWidget(left)

        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(10, 10, 10, 10)
        toolbar = QHBoxLayout()
        self.viewport_title = QLabel("Terrain & release geometry")
        self.viewport_title.setObjectName("Title")
        toolbar.addWidget(self.viewport_title)
        toolbar.addStretch()
        self.background = QComboBox()
        self.background.addItem("No background", "none")
        self.background.addItem("OpenStreetMap", "osm")
        self.background.addItem("Satellite imagery", "satellite")
        self.background.setToolTip("Optional online background. Requests visible tiles only; georeferenced terrain is required.")
        self.background.currentIndexChanged.connect(lambda _: self.map.basemap.set_provider(self.background.currentData()))
        toolbar.addWidget(self.background)
        for title, callback in (("Fit domain", lambda: self.map.fit_domain()),):
            button = QPushButton(title)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        centre_layout.addLayout(toolbar)
        self.map = MapView()
        self.map.styles = deepcopy(self.session.raster_styles)
        self.map.basemap.message.connect(self._append_log)
        self.map.styles_changed.connect(self._styles_changed)
        self.map.coordinate.connect(lambda text: self.coordinate_label.setText(text))
        self.map.extent_changed.connect(lambda extent: setattr(self.session, "map_extent", extent))
        self.map.profile_drawn.connect(self._profile_drawn)
        self.map.gauge_placed.connect(self._gauge_placed)
        self.map.geometry_changed.connect(self._geometry_changed)

        self.vertical = QSplitter(Qt.Vertical)
        self.vertical.addWidget(self.map)
        self.bottom = QTabWidget()
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2000)
        self.console.setPlaceholderText("Input diagnostics and native solver output appear here.")
        self.bottom.addTab(self.console, "Console && diagnostics")
        light = QApplication.instance().property("appearance") != "dark"
        pg.setConfigOption("foreground", "#36556c" if light else "#cddbe7")
        self.chart = pg.PlotWidget(background="#ffffff" if light else "#101b28")
        self.chart.showGrid(x=True, y=True, alpha=.15)
        self.chart.setLabel("bottom", "Distance", units="m")
        self.chart.setLabel("left", "Elevation", units="m")
        self.bottom.addTab(self.chart, "Profiles")
        self.gauge_chart = pg.PlotWidget(background="#ffffff" if light else "#101b28")
        self.gauge_chart.showGrid(x=True, y=True, alpha=.15)
        self.gauge_chart.setLabel("bottom", "Elapsed simulation time", units="s")
        self.bottom.addTab(self.gauge_chart, "Gauges")
        self.console_toggle = QPushButton("−")
        self.console_toggle.setToolTip("Minimize console & diagnostics")
        self.console_toggle.setFixedWidth(40)
        self.console_toggle.clicked.connect(self.toggle_console)
        self.bottom.setCornerWidget(self.console_toggle)
        self._console_collapsed = False
        self.bottom.tabBarClicked.connect(lambda _: self.toggle_console() if self._console_collapsed else None)
        self.vertical.addWidget(self.bottom)
        self.vertical.setSizes([630, 180])
        centre_layout.addWidget(self.vertical, 1)
        self.timeline = QWidget()
        timeline_layout = QVBoxLayout(self.timeline)
        timeline_layout.setContentsMargins(0, 7, 0, 0)
        self.dataset = QComboBox()
        self.dataset.addItem("Avalanche", "avac")
        self.dataset.addItem("Waves", "wave")
        self.dataset.addItem("Avalanche + water displacement", "combined")
        self.dataset.currentIndexChanged.connect(self._dataset_changed)
        timeline_layout.addWidget(QLabel("Results"))
        timeline_layout.addWidget(self.dataset)
        self.play = QPushButton("Play")
        self.play.clicked.connect(self._play_pause)
        previous = QPushButton("‹")
        previous.clicked.connect(lambda: self.slider.setValue(max(0, self.slider.value()-1)))
        following = QPushButton("›")
        following.clicked.connect(lambda: self.slider.setValue(min(self.slider.maximum(), self.slider.value()+1)))
        self.previous_frame, self.next_frame = previous, following
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._frame_changed)
        self.time_label = QLabel("No completed run selected")
        self.variable = QComboBox()
        for key in ("depth", "velocity", "pressure", "snow_surface_elevation"):
            self.variable.addItem(LABELS[key], key)
        self.variable.currentIndexChanged.connect(self._variable_changed)
        self.fps = QSpinBox()
        self.fps.setRange(1, 30)
        self.fps.setValue(5)
        self.fps.setSuffix(" fps")
        self.fps.valueChanged.connect(lambda fps: self.play_timer.setInterval(int(1000/fps)))
        timeline_layout.addWidget(QLabel("Display field"))
        timeline_layout.addWidget(self.variable)
        playback = QHBoxLayout()
        for widget in (previous, self.play, following):
            playback.addWidget(widget)
        timeline_layout.addLayout(playback)
        for widget in (self.slider, self.time_label, self.fps):
            timeline_layout.addWidget(widget)
        self.timeline.setEnabled(False)
        self.coordinate_label = muted("Import terrain to inspect coordinates and elevation.")
        centre_layout.addWidget(self.coordinate_label)
        self.horizontal.addWidget(centre)

        self.panels = ConfigurationPanels(self.session)
        self.panels.changed.connect(self._configuration_changed)
        self.panels.problem.connect(self._error)
        self._add_actions()
        scroll = self.panel_scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.panels)
        scroll.setMinimumWidth(335)
        self.horizontal.addWidget(scroll)
        self.horizontal.setSizes([205, 900, 365])
        self.horizontal.setStretchFactor(1, 1)
        layout.addWidget(self.horizontal, 1)
        self.setCentralWidget(root)
        self.status_label = QLabel("Unconfigured")
        self.status_label.setObjectName("Status")
        self.statusBar().addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setValue(0)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.global_stop = QPushButton("Stop / cancel")
        self.global_stop.setObjectName("Stop")
        self.global_stop.clicked.connect(self.stop)
        self.global_stop.setEnabled(False)
        self.statusBar().addPermanentWidget(self.global_stop)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(200)
        self.play_timer.timeout.connect(self._advance_frame)

    def _button(self, key, title, callback, primary=False):
        button = QPushButton(title.replace("&", "&&"))
        if primary:
            button.setObjectName("Primary")
        def clicked():
            self._action_generation += 1
            generation, session = self._action_generation, self.session
            def invoke():
                if generation != self._action_generation or self.session is not session:
                    return
                if self.tasks.active:
                    if self.tasks.active.passive:
                        self.play_timer.stop()
                        self.play.setText("Play")
                        QTimer.singleShot(20, invoke)
                    else:
                        self._error("Wait for the current data task to finish.")
                    return
                callback()
            invoke()
        button.clicked.connect(clicked)
        target = self.panels.layouts[key]
        target.insertWidget(target.count()-1, button)
        return button

    def _add_actions(self):
        self._button("terrain", "Import DEM", self.import_dem)
        self._button("terrain", "Import releases", self.import_release)
        self._button("terrain", "Export releases", self.export_releases)
        self._button("release", "Preview initial depth", self.preview_depth)
        self._button("release", "Preview initial snow surface", lambda: self.preview_depth(surface=True))
        self._button("numerics", "Edit complete configuration YAML", self.edit_yaml)
        self._button("numerics", "Load standard parameters", self.load_standard_parameters)
        release_layout = self.panels.layouts["release"]
        release_layout.removeWidget(self.panels.release_info)
        release_layout.insertWidget(release_layout.count()-1, self.panels.release_info)
        self.prepare_button = self._button("run", "Prepare", self.prepare_run, True)
        self.run_button = self._button("run", "Run", self.run_solver, True)
        self.run_button.setEnabled(False)
        self.run_button.setVisible(False)
        cpu = self.cpu = QSpinBox()
        cpu.setRange(1, os.cpu_count() or 1)
        cpu.setValue(self.session.threads)
        cpu.setSuffix(" CPU threads")
        cpu.valueChanged.connect(lambda value: setattr(self.session, "threads", value))
        self.panels.layouts["run"].insertWidget(2, cpu)
        self.panels.layouts["analyze"].insertWidget(1, self.timeline)
        self._button("profiles", "Draw profile · double-click to finish", lambda: self.map.set_tool("profile"))
        self._button("gauges", "Place point gauge", lambda: self.map.set_tool("gauge"))
        for kind, label in (("profile", "Profile"), ("gauge", "Gauge")):
            page = "profiles" if kind == "profile" else "gauges"
            self._button(page, f"Load {kind}s shapefile", self.load_sampling_shapes)
            selector = QComboBox()
            selector.setToolTip(f"Select a saved {kind} to inspect the current result.")
            setattr(self, f"{kind}_selector", selector)
            self.panels.layouts[page].insertWidget(self.panels.layouts[page].count()-1, QLabel(label))
            self.panels.layouts[page].insertWidget(self.panels.layouts[page].count()-1, selector)
            selector.currentIndexChanged.connect(lambda _, k=kind: self._sampling_selected(k))
            self._button(page, f"Export {kind}s shapefile", lambda checked=False, k=kind: self.save_sampling_shapes(k))
            self._button(page, f"Export {kind} CSV", self.export_csv)
            self._button(page, f"Export {kind} figure PNG", self.export_figure)
            if kind == "profile":
                self._button(page, "Export profile MP4", self.export_video)
        self._button("analyze", "Export current field GeoTIFF", self.export_raster)
        self._button("analyze", "Export map PNG", self.export_png)
        self._button("analyze", "Export map MP4", self.export_video)
        self._button("wave", "Import lake polygon", self.import_lake)
        self._button("wave", "Derive lake · click a basin on map", lambda: self.map.set_tool("lake"))
        self.map.lake_seed.connect(self._derive_lake)
        self._button("wave", "Preview initial WAVE depth", self.preview_wave)
        wave_layout = self.panels.layouts["wave"]
        grid = self.panels.wave_controls["cell_size"].parentWidget()
        wave_layout.removeWidget(grid)
        wave_layout.insertWidget(wave_layout.count()-1, grid)
        self._prepared_wave = None

    def _menus(self):
        chrome = QWidget()
        chrome_layout = QVBoxLayout(chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        chrome_layout.addWidget(self.title_bar)
        self.main_menu = QMenuBar()
        chrome_layout.addWidget(self.main_menu)
        self.setMenuWidget(chrome)
        menu = self.file_menu = self.main_menu.addMenu("File")
        for title, shortcut, callback in (("New project", "Ctrl+N", self.new_project), ("Open project…", "Ctrl+O", self.open_project),
                                          ("Save project", "Ctrl+S", self.save), ("Save project as…", "Ctrl+Shift+S", lambda: self.save(as_new=True)),
                                          ("Load standard parameters", "", self.load_standard_parameters),
                                          ("Load AVAC configuration…", "", self.load_yaml),
                                          ("Export AVAC configuration…", "", self.export_configuration),
                                          ("Exit", "Alt+F4", self.close)):
            action = QAction(title, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            menu.addAction(action)
        self.edit_menu = self.main_menu.addMenu("Edit")
        self.edit_menu.addAction("Settings…", self.edit_settings)
        self.extensions_menu = self.main_menu.addMenu("Extensions")
        self.wave_action = self.extensions_menu.addAction("Activate Impulse Wave")
        self.wave_action.setCheckable(True)
        self.wave_action.setChecked(self.session.wave_enabled)
        self.wave_action.toggled.connect(self._enable_wave)
        view = self.view_menu = self.main_menu.addMenu("View")
        view.addAction("Minimize / restore console", self.toggle_console)
        view.addAction("Raster appearance…", self.map.edit_raster_style)
        fit = view.addAction("Fit terrain")
        fit.setShortcut("F")
        fit.triggered.connect(self.map.fit_domain)
        panels = view.addAction("Toggle side panels")
        panels.setShortcut("Tab")
        panels.triggered.connect(self._toggle_panels)
        help_menu = self.help_menu = self.main_menu.addMenu("Help")
        help_menu.addAction("Load tutorial", self.load_tutorial)
        help_menu.addAction("License and scientific-use notice", self.show_license_notice)
        help_menu.addAction("About AVAC Desktop", lambda: QMessageBox.about(self, "AVAC Desktop", "AVAC Desktop 0.1.5\nFree software: AGPL-3.0-or-later.\nProvided without warranty, to the extent permitted by law.\nScientific desktop development build; not a certified hazard assessment.\nSee Help → License and scientific-use notice."))
        # PySide 6.8 can invalidate a menu when an ephemeral menuAction wrapper
        # is collected after QAction.menu(); retain those wrappers explicitly.
        self._menu_actions = self.main_menu.actions()

    def set_mode(self, mode: str):
        changed = self.session.mode != mode
        self.session.set_mode(mode)
        self.model_button.setChecked(mode == "model_run")
        self.analyze_button.setChecked(mode == "analyze")
        self.navigation.blockSignals(True)
        self.navigation.clear()
        self.nav_keys = ["terrain", "release", "material", "numerics", "run"] if mode == "model_run" else ["analyze", "profiles", "gauges"]
        names = ["01  Terrain & release", "02  Release conditions", "03  Material & rheology", "04  Numerics", "05  Run"] if mode == "model_run" else ["Map", "Profiles", "Gauges"]
        if mode == "model_run" and self.session.wave_enabled:
            self.nav_keys.insert(4, "wave")
            names[-1:] = ["05  Waves", "06  Run"]
        self.navigation.addItems(names)
        selected = self.nav_keys.index(self.session.result_page) if mode == "analyze" else 0
        self.navigation.setCurrentRow(selected)
        self.navigation.blockSignals(False)
        self.workflow_label.setText("  MODEL WORKFLOW" if mode == "model_run" else "  RESULTS")
        if mode == "model_run":
            self.bottom.setCurrentWidget(self.console)
        self.map.set_model_tools(mode == "model_run")
        if mode == "model_run" and self.map.tool in ("profile", "gauge"):
            self.map.set_tool("pan")
        self.timeline.setVisible(mode == "analyze")
        self.viewport_title.setText("Terrain & release geometry" if mode == "model_run" else "Map")
        self._navigate(selected)
        self._refresh_mesh()
        if changed:
            self.session.dirty = True

    def _navigate(self, row: int):
        if 0 <= row < len(self.nav_keys):
            key = self.nav_keys[row]
            self.panels.show_page(key)
            if self.session.mode == "analyze":
                self.session.result_page = key
                self.panels.layouts[key].insertWidget(1, self.timeline)
                self.timeline.show()
                self.bottom.setTabVisible(self.bottom.indexOf(self.chart), key == "profiles")
                self.bottom.setTabVisible(self.bottom.indexOf(self.gauge_chart), key == "gauges")
                if key in ("profiles", "gauges"):
                    if self._console_collapsed:
                        self.toggle_console()
                    self.bottom.setCurrentWidget(self.chart if key == "profiles" else self.gauge_chart)
                    self.map.setMinimumHeight(260)
                    self.vertical.setSizes([310, 500])
                else:
                    self.map.setMinimumHeight(0)
                    self.bottom.setCurrentWidget(self.console)
                    self.vertical.setSizes([650, 140])
            else:
                self.map.setMinimumHeight(0)
                self.bottom.setTabVisible(self.bottom.indexOf(self.chart), False)
                self.bottom.setTabVisible(self.bottom.indexOf(self.gauge_chart), False)
            self._resize_panel()

    def _resize_panel(self):
        self.panels.updateGeometry()
        QTimer.singleShot(0, lambda: self.panels.setMinimumHeight(self.panels.minimumSizeHint().height()))

    def _snapshot(self):
        snapshot = copy(self.session)
        snapshot.configuration = deepcopy(self.session.configuration)
        snapshot.wave_setup = deepcopy(self.session.wave_setup)
        return snapshot

    def _update_project(self):
        self.setWindowTitle(f"{self.session.name}{' •' if self.session.dirty else ''} — AVAC Desktop")
        if not self.session.terrain:
            self.panels.terrain_info.setText("Import a terrain DEM and release polygons to begin.\n\nParameters: " + ("loaded" if self.session.configuration else "none loaded — see File menu"))
            self.panels.release_info.setText("No release polygons loaded.")
        if self.session.terrain:
            raster = self.session.terrain.raster
            m = raster.metadata
            finite = np.isfinite(raster.z)
            crs_label = raster.crs_authid or "None (local XY; metres assumed)"
            self.panels.terrain_info.setText(f"{self.session.terrain.source.name}\n\nCRS: {crs_label}\nGrid: {m['ncols']:,} × {m['nrows']:,}\nNative cell: {m['cellsize']:g} m\nElevation: {np.nanmin(raster.z):.4g}–{np.nanmax(raster.z):.4g} m\nNoData: {100*(1-np.mean(finite)):.3g}%\nScientific array: {raster.z.nbytes/1024**2:.1f} MiB\n\nBounds [m]\nE {m['xmin']:.3f} … {m['xmax']:.3f}\nN {m['ymin']:.3f} … {m['ymax']:.3f}\n\nProject folder: {self.session.project_path.parent if self.session.project_path else 'Save the project to choose its folder'}")
            self.panels.release_info.setText(f"{len(self.session.rings)} polygons in {crs_label}\n{self.session.release_path or 'Import release polygons'}")

    def load_paths(self, dem: Path, release: Path | None = None, *, tutorial=False, preserve_project_state=False):
        if self.tasks.active or not self._can_replace():
            return
        self.status_label.setText("Loading terrain…")
        self.play_timer.stop()
        def work(task):
            terrain = read_terrain(dem)
            rings = read_polygons(release, terrain.wkt) if release else []
            release_hash = sha256_file(release) if release else None
            image, low, high = terrain_display(terrain)
            from .analysis_shapes import read_shapes
            features = []
            if preserve_project_state:
                for path in self.session.analysis_paths:
                    features.extend(read_shapes(path, terrain.raster.crs_authid))
            lake = read_polygons(self.session.lake_path, terrain.wkt) if self.session.lake_path else []
            return terrain, rings, image, low, high, release_hash, features, lake
        def loaded(bundle):
            terrain, rings, image, low, high, release_hash, features, self._lake_rings = bundle
            self.session.terrain, self.session.rings = terrain, rings
            self.session.release_path, self.session.release_hash = release, release_hash
            if not preserve_project_state:
                self.session.release_export_path = release
                self.session.release_edited = False
                self.session.sketch_lines = []
            self.session.dirty = not preserve_project_state
            self.session.prepared_run = None
            if not preserve_project_state:
                self.session.selected_run = None
                self.session.frame_index, self.session.variable = 0, "depth"
            self.results = None
            self.timeline.setEnabled(False)
            self.current_raster = None
            self.map.set_terrain(terrain, rings, image, low, high)
            self.map.set_sketch_lines(self.session.sketch_lines)
            if preserve_project_state:
                self.session.analysis_features = features
            self._refresh_sampling_selectors()
            self._restore_map_layers()
            self.status_label.setText("Terrain loaded")
            self._update_project()
            self.data_loaded.emit()
        self.tasks.submit(work, loaded)

    def load_tutorial(self):
        if not self._can_replace() or not self._confirm_unsaved():
            return
        from .app import resource_root
        root = resource_root()/"tutorial"
        if not all((root/name).is_file() for name in ("topo_cut_dam_1m.tif", "avalanches.geojson")):
            QMessageBox.information(self, "Tutorial files missing", "The tutorial is included in the Windows installer. Reinstall AVAC Desktop to restore missing files. For a source checkout, run python tools/fetch_tutorial.py, then choose Help > Load tutorial again.")
            return
        self._adopt(ProjectSession(name="Tutorial · Alpine avalanche", configuration=load_complete_configuration(default_template_path())))
        self.load_paths(root/"topo_cut_dam_1m.tif", root/"avalanches.geojson", tutorial=True)

    def load_standard_parameters(self):
        if not self._can_replace():
            return
        self._apply_configuration(default_configuration())

    def import_dem(self):
        if not self._can_replace():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import projected terrain", "", "Raster DEM (*.tif *.tiff *.asc);;All files (*)")
        if filename:
            self.load_paths(Path(filename))

    def import_release(self):
        if not self.session.terrain:
            self._error("Import a terrain DEM first so release geometries share its coordinates.")
            return
        if self.tasks.active or self.job.running:
            self._error("Finish the current task/run before replacing its inputs.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import release polygons", "", "Polygon data (*.geojson *.gpkg *.shp);;All files (*)")
        if filename:
            path = Path(filename)
            self.tasks.submit(lambda task: (read_polygons(path, self.session.terrain.wkt), sha256_file(path)),
                              lambda bundle: self._release_loaded(path, bundle))

    def _release_loaded(self, path, bundle):
        self.session.release_path, self.session.rings, self.session.release_hash = path, bundle[0], bundle[1]
        self.session.release_export_path = path
        self.map.set_release(self.session.rings)
        self.session.release_edited = False
        self._configuration_changed()

    def export_releases(self):
        if not self.session.terrain or not self.session.rings:
            self._error("Import or draw release polygons first.")
            return
        source = self.session.release_export_path or (self.session.release_path if not self.session.release_edited else None)
        suggested = str(source) if source else str((self.session.workspace or Path.cwd())/"releases.geojson")
        filename, _ = QFileDialog.getSaveFileName(self, "Export release polygons", suggested,
                                                "Polygon data (*.geojson *.gpkg *.shp)")
        if filename:
            from .geometry import export_release_polygons
            try:
                path = export_release_polygons(Path(filename), self.session.rings, self.session.terrain.raster.crs_authid)
                if self.session.release_path and path == self.session.release_path.resolve():
                    self.session.release_hash = sha256_file(path)
                    self._configuration_changed()
                self._append_log(f"Exported releases: {path}")
            except (ValueError, OSError, RuntimeError) as exc:
                self._error(str(exc))

    def _geometry_changed(self, rings, lines):
        if self.session.mode != "model_run" or self.tasks.active or self.job.running or not self.session.terrain:
            self._error("Finish the active task before editing preparation geometry.")
            self.map.set_release(self.session.rings)
            self.map.set_sketch_lines(self.session.sketch_lines)
            self.map.set_tool("pan")
            return
        try:
            from .geometry import release_geojson
            from .project import atomic_text
            from PySide6.QtCore import QStandardPaths
            import uuid
            polygon_changed = len(rings) != len(self.session.rings) or any(
                not np.array_equal(a[0], b[0]) or len(a[1]) != len(b[1]) or
                any(not np.array_equal(x, y) for x, y in zip(a[1], b[1]))
                for a, b in zip(rings, self.session.rings))
            if polygon_changed:
                text = release_geojson(rings, self.session.terrain.raster.crs_authid)
                # Changes are made to a new owned draft, never to an imported file.
                root = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/"drafts"/self.session.project_id
                path = root/f"releases-{uuid.uuid4().hex}.geojson" if rings else None
                if path:
                    atomic_text(path, text)
                self.session.release_path = path
                self.session.release_hash = sha256_file(path) if path else None
                self.session.release_edited = True
            self.session.rings = deepcopy(rings)
            self.session.sketch_lines = deepcopy(lines)
            self.map.set_release(rings)
            self.map.set_sketch_lines(lines)
            self._configuration_changed()
        except (ValueError, OSError, RuntimeError) as exc:
            self.map.set_release(self.session.rings)
            self.map.set_sketch_lines(self.session.sketch_lines)
            self.map.set_tool("pan")
            self._error(str(exc))

    def choose_workspace(self):
        # Compatibility for callers; projects now own their working directory.
        return self._require_saved_project()

    def _require_saved_project(self):
        if self.tasks.active or self.job.running:
            self._error("Finish the active task before saving and preparing a run.")
            return False
        if self.session.project_path is None:
            self._append_log("Save the project first; runs are stored in its folder.")
        return self.save()

    def export_configuration(self):
        if not self.session.configuration:
            self._error("Load parameters before exporting an AVAC configuration.")
            return
        if self.panels.timing_error:
            self._error(self.panels.timing_error)
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export AVAC configuration", "AVAC_configuration.yaml", "YAML (*.yaml *.yml)")
        if filename:
            from .project import atomic_text
            try:
                atomic_text(Path(filename), yaml.safe_dump(self.session.configuration, sort_keys=False))
                self._append_log(f"Exported AVAC configuration: {filename}")
            except (OSError, ValueError) as exc:
                self._error(str(exc))

    def edit_settings(self):
        from .settings_dialog import SettingsDialog
        from .theme import apply_theme
        from .preferences import appearance
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            apply_theme(QApplication.instance(), appearance())
            self.map.apply_appearance(appearance())
            self.map.basemap.set_provider(self.background.currentData())
            for chart in (self.chart, self.gauge_chart):
                chart.setBackground("#ffffff" if appearance() == "light" else "#101b28")
                chart.getAxis("left").setTextPen("#36556c" if appearance() == "light" else "#cddbe7")
                chart.getAxis("bottom").setTextPen("#36556c" if appearance() == "light" else "#cddbe7")
            self._resize_panel()

    def toggle_console(self):
        self._console_collapsed = not self._console_collapsed
        if self._console_collapsed:
            self._expanded_sizes = self.vertical.sizes()
            self.bottom.setMaximumHeight(self.bottom.tabBar().sizeHint().height()+4)
            self.console_toggle.setText("+")
            self.console_toggle.setToolTip("Restore console & diagnostics")
        else:
            self.bottom.setMaximumHeight(16777215)
            self.vertical.setSizes(getattr(self, "_expanded_sizes", [630, 180]))
            self.console_toggle.setText("−")
            self.console_toggle.setToolTip("Minimize console & diagnostics")

    def show_license_notice(self):
        from .app import resource_root
        dialog = QDialog(self)
        dialog.setWindowTitle("License and scientific-use notice")
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        root = resource_root()
        text.setPlainText((root/"DISCLAIMER.txt").read_text(encoding="utf-8")+"\n\n"+
                          (root/"LICENSE").read_text(encoding="utf-8"))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _styles_changed(self):
        self.session.raster_styles = deepcopy(self.map.styles)
        self.session.dirty = True

    def _layer(self, key, visible):
        changed = self.session.layers.get(key, key != "mesh") != visible
        self.session.layers[key] = visible
        item = {"terrain": self.map.terrain_item, "release": self.map.release_item, "lake": self.map.lake_item}.get(key)
        if item is not None:
            item.setVisible(visible)
        if key in ("profiles", "gauges"):
            self.map.set_analysis_visibility("profile" if key == "profiles" else "gauge", visible)
        if key in ("legends", "scale", "north"):
            self.map.decorations[key] = visible
            self.map.viewport().update()
        if key == "mesh":
            self._refresh_mesh()
        if changed:
            self.session.dirty = True

    def _restore_map_layers(self):
        self._update_background_availability()
        self.map.set_lake(self._lake_rings)
        self.layer_checks["lake"].setVisible(bool(self._lake_rings))
        for key, check in self.layer_checks.items():
            check.blockSignals(True)
            check.setChecked(self.session.layers.get(key, key != "mesh"))
            check.blockSignals(False)
            self._layer(key, check.isChecked())

    def _refresh_mesh(self):
        from .mesh import MeshSnapshot, inspect_initial_mesh
        preparation = self.session.mode == "model_run"
        self.layer_checks["mesh"].setVisible(preparation)
        if not preparation or not self.session.layers.get("mesh", False):
            self.map.set_mesh(None)
            return
        root = self.session.prepared_run
        if root is None or self.session.prepared_signature != simulation.signature(self.session):
            self.map.set_mesh(MeshSnapshot(notice="Prepare the run to inspect its initial mesh."))
            return
        if self._initial_mesh_run == root and self._initial_mesh is not None:
            self.map.set_mesh(self._initial_mesh)
            return
        if self.job.running:
            self.map.set_mesh(MeshSnapshot(notice="Prepare a new run to inspect its initial mesh."))
            return
        self.map.set_mesh(MeshSnapshot(notice="Building initial mesh; no time steps are taken…"))
        if self.tasks.active:
            self._pending_initial_mesh = True
            return
        snapshot = self._snapshot()
        expected_signature = snapshot.prepared_signature
        def done(mesh):
            if self.session.prepared_run != root or simulation.signature(self.session) != expected_signature:
                return
            if not mesh.layers:
                self._append_log(mesh.notice)
                if self.session.mode == "model_run" and self.session.layers.get("mesh", False):
                    self.map.set_mesh(mesh)
                return
            self._initial_mesh, self._initial_mesh_run = mesh, root
            levels = sorted(set(map(int, mesh.layers[0].patches[:, 6])))
            message = f"Initial AVAC mesh: levels {levels}, {len(mesh.layers[0].patches)} patches. No time steps taken."
            if max(levels) < int(snapshot.configuration['computation']['refinement']):
                message += " Warning: the initial mesh does not reach the requested refinement level. Check release depth and dry tolerance."
            self._append_log(message)
            if self.session.mode == "model_run" and self.session.layers.get("mesh", False):
                self.map.set_mesh(mesh)
        def work(task):
            try:
                return inspect_initial_mesh(snapshot, task)
            except (OSError, ValueError) as exc:
                return MeshSnapshot(notice=f"Initial mesh unavailable: {exc}")
        self.tasks.submit(work, done)

    def _update_background_availability(self):
        terrain = self.map.terrain
        available = terrain is None or has_geographic_reference(terrain)
        self.background.setEnabled(available)
        self.background.setToolTip("Optional online background. A geographic CRS is required." if available else
                                   "Backgrounds are unavailable for terrain without a geographic CRS.")
        if available:
            self._background_warning_key = None
            return
        self.background.blockSignals(True)
        self.background.setCurrentIndex(self.background.findData("none"))
        self.background.blockSignals(False)
        self.map.basemap.set_provider("none")
        key = (str(terrain.source), terrain.source_hash, terrain.wkt)
        if getattr(self, "_background_warning_key", None) != key:
            reason = "DEM has no CRS; coordinates and elevations are assumed to be metres" if not terrain.raster.crs_authid else "DEM uses a local Cartesian CRS"
            self._append_log(f"Warning: {reason}. Background maps and satellite imagery are disabled. "
                             "Imported release, lake, profile and gauge geometries use the same XY coordinates without reprojection.")
            self._background_warning_key = key

    def _configuration_changed(self):
        self.session.dirty = True
        self.run_button.setEnabled(False)
        self.run_button.setVisible(False)
        self.prepare_button.setVisible(True)
        self._prepared_wave = None
        self._run_plan = None
        self._update_project()
        self._refresh_mesh()

    def _task_error(self, text):
        self._sync_dataset_selector()
        if self._video_export:
            self._video_export._fail(text)
        self._pipeline_active = False
        self._run_plan = None
        self._error(text)

    def validate_inputs(self):
        snapshot = self._snapshot()
        def done(issues):
            self._append_log("Validation: " + ("\n".join(issues) if issues else "Inputs satisfy the current schema/grid preflight. Preview verifies release coverage and corrected depths."))
            self.status_label.setText("Invalid" if issues else "Ready to preview")
        self.tasks.submit(lambda task: simulation.validate(snapshot), done)

    def check_runtime(self):
        def work(task):
            root = ensure_runtime()
            manifest = validate_runtime(root)
            return root, manifest
        def done(result):
            root, manifest = result
            self._append_log(f"Verified native runtime: {root}\nSolver: {manifest['solver']}")
        self.tasks.submit(work, done)

    def preview_depth(self, checked=False, *, surface=False):
        snapshot = self._snapshot()
        def done(result):
            raster, coverage, depth = result
            values = initial_snow_surface_elevation(raster, depth) if surface else depth
            self.current_raster = AvacRaster(raster.x, raster.y, values, raster.metadata, raster.crs_authid, 1)
            self.current_variable = "snow_surface_elevation" if surface else "depth"
            self.current_time = None
            self.map.set_field(self.current_raster, "Initial snow surface [m]" if surface else "Initial mobile depth [m]")
            self._sample_profile()
            self.status_label.setText("Initial state previewed")
            cell = float(raster.metadata["cellsize"])
            self._append_log(f"Exact scientific preview: max depth {np.max(depth):.9g} m; release footprint {np.sum(coverage)*cell**2:.9g} m²; initial mobile volume {np.sum(depth)*cell**2:.9g} m³.")
        self.tasks.submit(lambda task: simulation.preview(snapshot, task), done)

    def _show_terrain(self):
        if self.session.terrain:
            self.current_raster = None
            self.current_variable = "terrain_elevation"
            self.current_time = None
            self.map.clear_field()

    def prepare_run(self):
        if self.job.running:
            self._error("Wait for the current simulation to finish before preparing another run.")
            return
        if not self._require_saved_project():
            return
        if self.panels.timing_error:
            self._error(self.panels.timing_error)
            return
        snapshot = self._snapshot()
        self.status_label.setText("Preparing…")
        self._run_plan = None
        self.session.prepared_signature = None
        def done(result):
            self._run_plan = result
            if result["avac"]:
                self.session.prepared_run = result["avac"]["prepared"].run_root
                self.session.prepared_signature = result["avac"]["signature"]
                message = "AVAC prepared. WAVE will be staged and run automatically after AVAC completes." if snapshot.wave_enabled else "Native controls and exact initial state are staged."
            else:
                self.session.selected_run = result["source"]
                message = f"Matching completed avalanche reused:\n{result['source']}\n\nWAVE prepared:\n{result['wave'][0]}"
            self.panels.run_info.setText(message)
            self._refresh_mesh()
            self.status_label.setText("Prepared")
            self._append_log(message)
        def work(worker):
            worker.signals.progress.emit(2)
            issues = simulation.validate(snapshot)
            if issues:
                raise ValueError("\n".join(issues))
            if worker.cancelled.is_set():
                raise ValueError("Preparation cancelled.")
            runtime = ensure_runtime()
            manifest = validate_runtime(runtime)
            worker.signals.progress.emit(5)
            if worker.cancelled.is_set():
                raise ValueError("Preparation cancelled.")
            return workflow.prepare(snapshot, worker)
        self._append_log("Prepare: validating inputs, verifying the native runtime, then staging the isolated run.")
        task = self.tasks.submit(work, done)
        task.signals.progress.connect(lambda value: self.progress_bar.setValue(int(value)))

    def run_solver(self):
        if self.session.project_path is None or not self.session.project_path.is_file():
            self._error("Save the project before running a simulation.")
            return
        if self.session.wave_enabled and self._run_plan is None:
            self._error("Prepare the coupled scenario before running.")
            return
        snapshot = self._snapshot()
        def done(result):
            root, solver, kind = result
            self._pipeline_active = snapshot.wave_enabled
            self._pipeline_snapshot = snapshot
            self._start_saved_job(root, solver, kind)
        self.tasks.submit(lambda task: workflow.verify(snapshot, self._run_plan) if self._run_plan else (*simulation.verify_ready(snapshot), "AVAC"), done)

    def _start_saved_job(self, root, solver, kind):
        from .project import record_execution
        try:
            record_execution(self.session, root, kind)
            self.job.start(root, solver, self.session.threads, kind=kind)
        except (OSError, ValueError, KeyError) as exc:
            self._pipeline_active = False
            self._run_plan = None
            self._error(f"Could not record/start the simulation: {exc}")

    def stop(self):
        self._action_generation += 1
        self._pipeline_active = False
        if self.job.running:
            self.job.stop()
        self.tasks.cancel()
        if self._video_export:
            self._video_export.cancel()

    def _busy(self, busy: bool):
        self.panels.setEnabled(not busy and not self._pipeline_active and not self._video_export)
        self.wave_action.setEnabled(not busy and not self.job.running and not self._pipeline_active)
        self.progress_bar.setRange(0, 0 if busy else 100)
        if not busy:
            self.progress_bar.setValue(0)
        ready_plan = self._run_plan is not None
        self.run_button.setEnabled(not busy and not self.job.running and not self._pipeline_active and
                                   (ready_plan or (not self.session.wave_enabled and self.session.prepared_run is not None and self.session.prepared_signature == simulation.signature(self.session))))
        ready = self.run_button.isEnabled()
        self.run_button.setVisible(ready)
        self.prepare_button.setVisible(not ready)
        self.global_stop.setEnabled(self.job.running or busy)
        self.prepare_button.setEnabled(not busy and not self.job.running and not self._pipeline_active)

    def _task_finished(self, busy):
        if not busy:
            self.global_stop.setEnabled(self.job.running or self._pipeline_active or self._video_export is not None)
        if not busy and self._pending_initial_mesh:
            self._pending_initial_mesh = False
            QTimer.singleShot(0, self._refresh_mesh)
            return
        if self._pending_frame and not busy:
            self._pending_frame = False
            QTimer.singleShot(0, lambda: self._frame_changed(self.slider.value()))
        elif not busy and not self._pipeline_active and not self._video_export:
            QTimer.singleShot(0, self._sample_gauge)

    def _job_state(self, state):
        self.status_label.setText(state.capitalize())
        self.global_stop.setEnabled(state == "running")
        self.run_button.setEnabled(False)
        self.run_button.setVisible(False)
        self.prepare_button.setVisible(True)
        self.prepare_button.setEnabled(state != "running")
        if state == "running":
            self.session.prepared_signature = None
            self.wave_action.setEnabled(False)
        elif state in ("failed", "cancelled"):
            self._pipeline_active = False
            self._run_plan = None
            self.panels.setEnabled(True)
            self.wave_action.setEnabled(True)

    def _job_progress(self, count, total):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(count)
        self.status_label.setText(f"Running · {count}/{total} output frames")

    def _run_completed(self, root):
        recorded = False
        if self.session.project_path:
            from .project import record_completed_results
            try:
                record_completed_results(self.session, root, self.job.kind)
                recorded = True
                self._append_log("Completed results recorded in the project automatically.")
            except (OSError, ValueError, KeyError) as exc:
                self._error(f"Results are safe at {root}, but their project links could not be saved: {exc}. Use File → Save project before closing.")
        if self.job.kind == "WAVE":
            self.session.selected_wave = root
            self.session.dirty |= not recorded
            self._pipeline_active = False
            self._run_plan = None
            self._load_results("combined", root)
            return
        self.session.selected_run = root
        self.session.selected_wave = None
        if root not in self.session.runs:
            self.session.runs.append(root)
        self.session.dirty |= not recorded
        if self._pipeline_active:
            self._pipeline_snapshot.selected_run = root
            QTimer.singleShot(0, self._continue_wave)
            return
        self._run_plan = None
        self.load_run(root)

    def _continue_wave(self):
        if not self._pipeline_active:
            return
        if self.tasks.active:
            QTimer.singleShot(10, self._continue_wave)
            return
        self.status_label.setText("Preparing WAVE coupling…")
        self._append_log("AVAC completed. Preparing conservative shoreline coupling and WAVE automatically.")
        def done(result):
            if self._pipeline_active:
                self._start_saved_job(*result, "WAVE")
        self.tasks.submit(lambda task: workflow.continue_wave(self._pipeline_snapshot, self._run_plan, task), done)

    def _enable_wave(self, enabled):
        self.session.wave_enabled = enabled
        self.panels.refresh()
        self._configuration_changed()
        self.set_mode(self.session.mode)

    def import_lake(self):
        if self.tasks.active or self.job.running or not self.session.terrain:
            self._error("Load terrain and finish the active task before changing the lake polygon.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import lake polygon", "", "Polygon data (*.gpkg *.geojson *.shp)")
        if filename:
            path = Path(filename)
            def done(rings):
                self.session.lake_path = path
                self._lake_rings = rings
                self._restore_map_layers()
                self._configuration_changed()
                self.panels.wave_info.setText(f"Lake polygon: {path}\nAVAC source: {self.session.selected_run or 'Computed automatically when this project runs'}")
            self.tasks.submit(lambda task: read_polygons(path, self.session.terrain.wkt), done)

    def _derive_lake(self, x, y):
        if not self._require_saved_project():
            return
        from .wave import derive_lake
        snapshot = self._snapshot()
        def done(bundle):
            path, self._lake_rings = bundle
            self.session.lake_path = path
            self._restore_map_layers()
            self._configuration_changed()
            self.panels.wave_info.setText(f"Derived connected lake: {path}\nWater elevation: {self.session.wave_setup['water_level']} m")
            self.map.set_tool("pan")
        def work(task):
            path = derive_lake(snapshot, x, y)
            return path, read_polygons(path, snapshot.terrain.wkt)
        self.tasks.submit(work, done)

    def preview_wave(self):
        from .wave import preview_lake
        snapshot = self._snapshot()
        def done(result):
            lake, rings = result
            r = lake.raster
            self.current_raster = AvacRaster(r.x, r.y, lake.initial_depth, r.metadata, r.crs_authid, 1)
            self.current_variable, self.current_time = "water_depth", None
            self.map.set_field(self.current_raster, "Initial WAVE water depth [m]")
            self._sample_profile()
            self._append_log(f"WAVE lake preview: {lake.shoreline_faces.shape[0]} internal shoreline faces; {lake.stabilized_cells} cells stabilized by existing solver-grid preparation.")
        self.tasks.submit(lambda task: preview_lake(snapshot), done)

    def load_wave(self, root, *, restore_selection=False):
        return self._load_results("wave", Path(root), restore_selection=restore_selection)

    def load_run(self, path, *, restore_selection=False):
        return self._load_results("avac", Path(path), restore_selection=restore_selection)

    def _dataset_changed(self):
        kind = self.dataset.currentData()
        if kind == self.session.analysis_kind:
            return
        if self.tasks.active or self._video_export:
            self._sync_dataset_selector()
            self._error("Finish the current data task before switching results.")
            return
        path = self.session.selected_run if kind == "avac" else self.session.selected_wave
        if path is None:
            self._sync_dataset_selector()
            self._error("This project has no completed results for that view. Run the simulation or open a project with completed results.")
            return
        self._load_results(kind, path, reuse_sources=True)

    def _sync_dataset_selector(self):
        self.dataset.blockSignals(True)
        available = {"avac": bool(self.session.selected_run), "wave": bool(self.session.selected_wave),
                     "combined": bool(self.session.selected_run and self.session.selected_wave)}
        for index in range(self.dataset.count()):
            item = self.dataset.model().item(index)
            enabled = available[self.dataset.itemData(index)]
            item.setEnabled(enabled)
            item.setToolTip("" if enabled else "No completed results for this view in the loaded project.")
        self.dataset.setCurrentIndex(self.dataset.findData(self.session.analysis_kind))
        self.dataset.blockSignals(False)

    def _load_results(self, kind, root, *, restore_selection=False, reuse_sources=False):
        from .wave import WaveResults
        from .combined import CombinedResults
        from .sampling_cache import dataset_identity
        if self.tasks.active or self._video_export:
            self._error("Wait for the current task before opening results.")
            return
        desired_variable = self.session.variable if restore_selection else ("surface_displacement" if kind in ("wave", "combined") else "depth")
        desired_index = self.session.frame_index if restore_selection else 0
        snapshot = self._snapshot()
        sources = dict(self._result_sources) if reuse_sources else {}
        map_terrain = self.map.terrain
        current_lake = self._lake_rings
        self._stop_playback()
        def work(task):
            from avac_desktop.core.preprocessing import read_avac_topography
            from avac_desktop.core.run_project import read_run_metadata
            from .geo import Terrain
            def source(source_kind, path):
                path = Path(path).resolve()
                marker_path = path/(".avac_qgis_run.json" if source_kind == "avac" else ".avac_qgis_wave_run.json")
                output = path/("AVAC" if source_kind == "avac" else "Wave")/"_output"
                stat = marker_path.stat()
                stamp = stat.st_mtime_ns, stat.st_size, output.stat().st_mtime_ns
                cached = sources.get(source_kind)
                if cached is None or cached[:2] != (path, stamp):
                    result = Results(path) if source_kind == "avac" else WaveResults(path)
                    cached = path, stamp, result, dataset_identity(result)
                    sources[source_kind] = cached
                return cached[2], cached[3]
            avac_root, wave_root = snapshot.selected_run, snapshot.selected_wave
            marker = {}
            if kind in ("wave", "combined"):
                wave_root = root
                marker = json.loads((root/".avac_qgis_wave_run.json").read_text(encoding="utf-8"))
                from avac_desktop.core.wave_project import resolve_wave_source
                avac_root = resolve_wave_source(root, marker)
                water, identity = source("wave", wave_root)
                if kind == "combined":
                    avalanche, _ = source("avac", avac_root)
                    result = CombinedResults(avalanche, water)
                else:
                    result = water
            else:
                avac_root = root
                result, identity = source("avac", root)
            if snapshot.terrain:
                terrain = snapshot.terrain
            else:
                topo = avac_root/"Topo"/"topography.asc"
                terrain = map_terrain if map_terrain and map_terrain.source == topo else Terrain(
                    topo, read_avac_topography(topo, result.discovery.crs_authid), "", "")
            if terrain.raster.crs_authid != result.discovery.crs_authid:
                raise ValueError("Run CRS differs from the current project. Open it in a new project.")
            rings = snapshot.rings
            if not rings:
                metadata = read_run_metadata(avac_root)
                release = Path(metadata.get("release_layer", ""))
                if release.is_file():
                    rings = read_polygons(release, terrain.raster.crs_authid)
            lake_path = snapshot.lake_path
            if marker.get("lake_polygon"):
                # Prefer the lake belonging to the completed scenario over a
                # possibly edited current preparation polygon.
                lake_path = wave_root/marker["lake_polygon"]
            lake = read_polygons(lake_path, terrain.raster.crs_authid) if lake_path else (
                water.lake_outline() if kind in ("wave", "combined") else current_lake)
            index = min(max(desired_index, 0), len(result.discovery.frames)-1)
            variables = self._result_variables(result, kind)
            variable = desired_variable if desired_variable in variables else variables[0]
            frame = self._read_frame(result, variable, index)
            image = None if terrain is map_terrain else terrain_display(terrain)
            return result, frame, terrain, image, index, self._read_sampling_paths(terrain.raster.crs_authid), lake, rings, identity, avac_root, wave_root, variable, variables
        def done(bundle):
            (self.results, frame, terrain, image, index, features, self._lake_rings, rings,
             self._dataset_identity, avac_root, wave_root, variable, variables) = bundle
            self.session.analysis_features = features
            self._result_sources = sources
            self.session.selected_run, self.session.selected_wave = avac_root, wave_root
            self.session.analysis_kind = kind
            self.session.variable, self.session.frame_index = variable, index
            extent = self.session.map_extent
            if image is not None:
                self.map.set_terrain(terrain, rings, *image)
            else:
                self.map.set_release(rings)
            if extent:
                self.map.restore_extent(extent)
            self.map.set_sketch_lines(self.session.sketch_lines)
            self._restore_map_layers()
            self._refresh_sampling_selectors()
            self._sync_dataset_selector()
            self.slider.blockSignals(True)
            self.slider.setRange(0, len(self.results.discovery.frames)-1)
            self.slider.setValue(index)
            self.slider.blockSignals(False)
            self.variable.blockSignals(True)
            self.variable.clear()
            for key in variables:
                self.variable.addItem(LABELS[key], key)
            self.variable.setCurrentIndex(self.variable.findData(variable))
            self.variable.blockSignals(False)
            self.timeline.setEnabled(True)
            self._display_frame(frame)
        self.tasks.submit(work, done)

    @staticmethod
    def _result_variables(result, kind):
        if kind == "combined":
            return ["surface_displacement"]
        variables = [] if kind == "wave" else ["depth", "velocity", "pressure", "snow_surface_elevation"]
        if kind != "wave" and result.discovery.fgmax_path:
            variables.extend(("max_depth", "max_velocity", "max_pressure"))
            events = {"time_of_maximum_depth": "time_max_depth", "time_of_maximum_velocity": "time_max_velocity", "arrival_time": "arrival_time"}
            variables.extend(events[key] for key in result.discovery.fgmax_optional_quantities if key in events)
        if kind == "wave":
            variables.extend(("water_depth", "water_elevation", "surface_displacement"))
        return variables

    @staticmethod
    def _read_frame(results, variable, index):
        if hasattr(results, "overlays"):
            overlays = results.overlays(variable, index)
            return overlays[1], overlays
        return results.raster(variable, index), None

    def _display_frame(self, frame):
        (time, raster), overlays = frame
        self.current_raster = raster
        self.current_variable, self.current_time = self.session.variable, time
        self.map.clear_additional_fields()
        if overlays:
            snow, water = overlays
            self.map.set_field(snow[1], LABELS["depth"], hide_rings=self._lake_rings)
            if water:
                self.map.set_additional_field(water[1], LABELS["surface_displacement"])
        else:
            self.map.set_field(raster, LABELS[self.session.variable])
        self.time_label.setText(f"t = {time:.1f} s" if time is not None else "Full-run summary")
        self.map.time_text = self.time_label.text()
        self._update_temporal_controls()
        self.map.set_analysis_features(self.session.analysis_features)
        self._sample_profile()

    def _read_sampling_paths(self, crs):
        from .analysis_shapes import read_shapes
        paths = dict.fromkeys([*self.session.analysis_paths, *(f["path"] for f in self.session.analysis_features)])
        return [feature for path in paths for feature in read_shapes(path, crs)]

    def _stop_playback(self):
        self.play_timer.stop()
        self.play.setText("Play")
        self._pending_frame = False
        self._gauge_cache_key = None

    def _frame_changed(self, index):
        if not self.results:
            return
        self.session.frame_index = index
        if self.tasks.active:
            self._pending_frame = True
            return
        results, variable = self.results, self.session.variable
        def done(frame):
            if self.results is results and self.session.variable == variable and self.session.frame_index == index:
                self._display_frame(frame)
        self.tasks.submit(lambda task: self._read_frame(results, variable, index), done, passive=True)

    def _variable_changed(self):
        if self.variable.currentData():
            self.session.variable = self.variable.currentData()
            self._update_temporal_controls()
            self._gauge_cache_key = None
            self.gauge = None
            self.gauge_chart.clear()
            self._frame_changed(self.slider.value())

    def _is_temporal(self):
        return self.session.variable in ("depth", "velocity", "pressure", "snow_surface_elevation", "water_depth", "water_elevation", "surface_displacement")

    def _update_temporal_controls(self):
        temporal = bool(self.results) and self._is_temporal()
        for control in (self.play, self.slider, self.fps, self.previous_frame, self.next_frame):
            control.setEnabled(temporal)
        if not temporal:
            self.play_timer.stop()
            self.play.setText("Play")
            self.gauge_chart.clear()
            self.gauge_chart.setTitle("Gauges require a time-dependent result")
            self.gauge_chart.setLabel("left", "")
            self.gauge = None
            if self.profile_selector.currentData() and self.bottom.currentWidget() is self.gauge_chart:
                self.bottom.setCurrentWidget(self.chart)
        elif not self.play_timer.isActive():
            self.play.setText("Reset" if self.slider.value() == self.slider.maximum() else "Play")

    def _play_pause(self):
        if self._video_export:
            return
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.play.setText("Play")
        elif self.results and self._is_temporal():
            if self.slider.value() == self.slider.maximum():
                self.slider.setValue(0)
                self.play.setText("Play")
                return
            self.play_timer.start()
            self.play.setText("Pause")

    def _advance_frame(self):
        if self.tasks.active:
            return
        if self.slider.value() == self.slider.maximum():
            self.play_timer.stop()
            self.play.setText("Reset")
        else:
            self.slider.setValue(self.slider.value()+1)

    def _profile_drawn(self, coords):
        if not self._store_sampling_feature("profile", coords):
            return
        self._sample_profile()
        self._select_result_page("profiles")
        self.bottom.setCurrentWidget(self.chart)

    def _sample_profile(self):
        feature = self.profile_selector.currentData()
        if not feature:
            return
        coords = feature["coords"]
        raster = self.current_raster or (self.session.terrain.raster if self.session.terrain else None)
        if raster is None:
            return
        variable = self.current_variable if self.current_raster is not None else "terrain_elevation"
        # Core profile unit keys describe temporal quantities. Summary sampling
        # retains the summary label in the chart and compatible physical units.
        profile_key = {"max_depth": "depth", "max_velocity": "velocity", "max_pressure": "pressure", "water_depth": "depth"}.get(variable, variable)
        event_time = variable in ("time_max_depth", "time_max_velocity", "arrival_time")
        if event_time:
            profile_key = "depth"  # Reuse bilinear geometry sampling, with explicit time units below.
        time = self.current_time
        source = getattr(self.results, "root", None) or self.session.selected_run or (self.session.terrain.source if self.session.terrain else "Terrain")
        from .sampling_cache import cache_path, profile_cached
        identity = self._dataset_identity if self.results and self.current_variable == self.session.variable else simulation.signature(self.session)
        path = cache_path(self.session.workspace, feature, identity, variable, time)
        if event_time:
            profile_key = "event_time"
        self.profile = profile_cached(path, feature, raster, profile_key, source, time, LABELS.get(variable, variable))
        self.chart.clear()
        self.chart.plot(self.profile.distance_m, self.profile.values, pen=pg.mkPen("#53cbf3", width=2))
        self.chart.setLabel("bottom", "Distance", units="m")
        self.chart.setLabel("left", LABELS.get(variable, variable))
        stamp = f" · t = {time:.1f} s" if time is not None else ""
        self.chart.setTitle(f"{feature['name']} · {LABELS.get(variable, variable)}{stamp}")
        self._save_sample_figure(self.chart, path)

    def _gauge_placed(self, x, y):
        if not self.results or not self._is_temporal():
            self._error("Open a project with completed results and select a temporal variable before placing a gauge.")
            return
        if not self._store_sampling_feature("gauge", [[x, y]]):
            return
        self._sample_gauge()
        self._select_result_page("gauges")
        self.bottom.setCurrentWidget(self.gauge_chart)
        self.map.set_tool("pan")

    def _sample_gauge(self):
        feature = self.gauge_selector.currentData()
        if not feature or not self.results or not self._is_temporal() or self.tasks.active or self._video_export:
            return
        x, y = feature["coords"][0]
        results, variable = self.results, self.session.variable
        key = (id(results), variable, x, y)
        if getattr(self, "_gauge_cache_key", None) == key:
            return
        self._gauge_cache_key = key
        from .sampling_cache import cache_path, gauge_cached
        path = cache_path(self.session.workspace, feature, self._dataset_identity, variable)
        def done(data):
            if self.results is not results or self.session.variable != variable or self.gauge_selector.currentData() != feature:
                self._gauge_cache_key = None
                return
            self.gauge = (data[0], data[1], variable, x, y, getattr(results, "root", None) or results.discovery.run_root)
            self.gauge_chart.clear()
            self.gauge_chart.plot(*data, pen=pg.mkPen("#53cbf3", width=2))
            self.gauge_chart.setLabel("left", LABELS[variable])
            self.gauge_chart.setTitle(f"{feature['name']} · E {x:.3f}, N {y:.3f}")
            self._save_sample_figure(self.gauge_chart, path)
        self.global_stop.setEnabled(True)
        self.tasks.submit(lambda task: gauge_cached(path, results, feature, variable, task), done, passive=True)

    def _select_result_page(self, page):
        if self.session.mode == "analyze":
            self.navigation.setCurrentRow(self.nav_keys.index(page))

    def _save_sample_figure(self, chart, path):
        figure = path.with_name("figure.png")
        def save():
            if not figure.exists():
                chart.grab().save(str(figure))
        # Capture after pyqtgraph has completed its layout. Each saved figure
        # belongs to the exact sample key, including geometry/run/field/time.
        generation = self.profile if chart is self.chart else self.gauge
        QTimer.singleShot(0, lambda: save() if generation is (self.profile if chart is self.chart else self.gauge) else None)

    def _store_sampling_feature(self, kind, coords):
        if not self.session.workspace and not self._require_saved_project():
            return False
        raster = self.current_raster or (self.session.terrain.raster if self.session.terrain else None)
        if raster is None:
            self._error("Load terrain or results before creating sampling geometries.")
            return False
        from .analysis_shapes import store_feature
        try:
            number = sum(feature["kind"] == kind for feature in self.session.analysis_features)+1
            feature = store_feature(self.session.workspace, kind, coords, f"{kind.title()} {number}", raster.crs_authid)
            self.session.analysis_features.append(feature)
            self.session.dirty = True
            self._refresh_sampling_selectors(feature)
            self._append_log(f"Saved {kind} shapefile: {feature['path']}")
            return True
        except (OSError, ValueError, RuntimeError) as exc:
            self._error(str(exc))
            return False

    def _refresh_sampling_selectors(self, selected=None):
        for kind in ("profile", "gauge"):
            selector = getattr(self, f"{kind}_selector")
            current = selected if selected and selected["kind"] == kind else selector.currentData()
            selector.blockSignals(True)
            selector.clear()
            for feature in self.session.analysis_features:
                if feature["kind"] == kind:
                    selector.addItem(feature["name"], feature)
                    if feature == current:
                        selector.setCurrentIndex(selector.count()-1)
            selector.blockSignals(False)
        self.map.set_analysis_features(self.session.analysis_features)

        for key, kind in (("profiles", "profile"), ("gauges", "gauge")):
            self.layer_checks[key].setVisible(any(f["kind"] == kind for f in self.session.analysis_features))
            self.map.set_analysis_visibility(kind, self.session.layers.get(key, True))

    def _sampling_selected(self, kind):
        if kind == "profile":
            self._sample_profile()
        else:
            self._gauge_cache_key = None
            self._sample_gauge()

    def load_sampling_shapes(self):
        if self.tasks.active:
            return
        raster = self.current_raster or (self.session.terrain.raster if self.session.terrain else None)
        if raster is None:
            self._error("Load terrain or results to set the sampling CRS first.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Load profiles or gauges", "", "Shapefile (*.shp)")
        if filename:
            from .analysis_shapes import read_shapes
            def done(features):
                existing = {(str(f['path']), f['fid']) for f in self.session.analysis_features}
                self.session.analysis_features.extend(f for f in features if (str(f['path']), f['fid']) not in existing)
                self.session.dirty = True
                self._refresh_sampling_selectors(features[0])
                self._sample_profile()
            self.tasks.submit(lambda task: read_shapes(Path(filename), raster.crs_authid), done)

    def save_sampling_shapes(self, kind):
        features = [f for f in self.session.analysis_features if f["kind"] == kind]
        if not features:
            self._error(f"Create or load a {kind} first.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, f"Save {kind}s shapefile", f"{kind}s.shp", "Shapefile (*.shp)")
        if filename:
            from .analysis_shapes import write_shapes
            raster = self.current_raster or self.session.terrain.raster
            try:
                path = write_shapes(Path(filename), features, raster.crs_authid)
                self._append_log(f"Saved {len(features)} {kind}(s): {path}")
            except (ValueError, OSError, RuntimeError) as exc:
                self._error(str(exc))

    def export_csv(self):
        gauge_subject = self.session.result_page == "gauges"
        if (self.gauge if gauge_subject else self.profile) is None:
            self._error("Select a computed gauge first." if gauge_subject else "Select a computed profile first.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export scientific samples", "samples.csv", "CSV (*.csv)")
        if filename:
            if not gauge_subject:
                write_profile_csv(filename, self.profile)
            else:
                write_gauge(Path(filename), *self.gauge)
            self._append_log(f"Exported {filename}")

    def export_raster(self):
        if self.current_raster is None:
            self._error("Select a result field or calculate an initial-state preview first.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export current field (Float32 GeoTIFF)", "field.tif", "GeoTIFF (*.tif)")
        if filename:
            raster = self.current_raster
            self.tasks.submit(lambda task: export_geotiff(Path(filename), raster), lambda _: self._append_log(f"Exported {filename}"))

    def export_png(self):
        if not self.map.terrain:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export current map extent with legend", "map.png", "PNG (*.png)")
        if filename:
            if not self.map.export_image().save(filename):
                self._error(f"Cannot save map: {filename}")

    def export_figure(self):
        gauge = self.session.result_page == "gauges"
        if (self.gauge if gauge else self.profile) is None:
            self._error("Select a computed profile or gauge first.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export figure", "gauge.png" if gauge else "profile.png", "PNG (*.png)")
        if filename:
            chart = self.gauge_chart if gauge else self.chart
            chart.grab().save(filename)

    def export_video(self):
        page = self.session.result_page
        if page == "gauges":
            return
        if not self.results or not self._is_temporal():
            self._error("Select a time-dependent result before exporting MP4.")
            return
        if page == "profiles" and self.profile is None:
            self._error("Select a computed profile first.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export animation", {"analyze": "map.mp4", "profiles": "profile.mp4"}[page], "MP4 (*.mp4)")
        if filename:
            self.start_video_export(Path(filename))

    def start_video_export(self, path):
        from .video_export import VideoExport
        if self.session.result_page == "gauges":
            return
        if self.tasks.active or self._video_export or not self.results or not self._is_temporal():
            self._error("Finish the current task and select a temporal result before exporting MP4.")
            return
        self._stop_playback()
        page = self.session.result_page
        original = self.slider.value()
        chart = self.chart
        size = self.map.viewport().size() if page == "analyze" else chart.size()
        def render(index, ready):
            if self._video_export is None:
                return
            if self.tasks.active:
                QTimer.singleShot(5, lambda: render(index, ready))
                return
            results, variable = self.results, self.session.variable
            def done(frame):
                if self._video_export is None:
                    return
                self.session.frame_index = index
                self.slider.blockSignals(True)
                self.slider.setValue(index)
                self.slider.blockSignals(False)
                self._display_frame(frame)
                # Let pyqtgraph lay out the current frame before capturing.
                QTimer.singleShot(0, lambda: ready(self.map.export_image() if page == "analyze" else chart.grab().toImage()))
            self.tasks.submit(lambda task: self._read_frame(results, variable, index), done, passive=True)
        video = self._video_export = VideoExport(path, size, self.fps.value(), len(self.results.discovery.frames), render, self)
        def cleanup():
            self._video_export = None
            self.navigation.setEnabled(True)
            self.horizontal.widget(0).setEnabled(True)
            self.main_menu.setEnabled(True)
            self.model_button.setEnabled(True)
            self.analyze_button.setEnabled(True)
            self.map.setEnabled(True)
            self._busy(self.tasks.active is not None and not self.tasks.active.passive)
            self.slider.blockSignals(True)
            self.slider.setValue(original)
            self.slider.blockSignals(False)
            self._frame_changed(original)
            QTimer.singleShot(0, video.deleteLater)
        def finished(filename):
            cleanup()
            self.status_label.setText("MP4 exported")
            self._append_log(f"Exported animation: {filename}")
        def failed(message):
            cleanup()
            self._error(message)
        video.finished.connect(finished)
        video.failed.connect(failed)
        video.progress.connect(lambda done, total: (self.progress_bar.setRange(0, total), self.progress_bar.setValue(done), self.status_label.setText(f"Exporting MP4 · {done}/{total}")))
        self.panels.setEnabled(False)
        self.navigation.setEnabled(False)
        self.horizontal.widget(0).setEnabled(False)
        self.main_menu.setEnabled(False)
        self.model_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.map.setEnabled(False)
        self.global_stop.setEnabled(True)
        video.start()

    def edit_yaml(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Advanced · complete AVAC YAML")
        dialog.resize(750, 750)
        layout = QVBoxLayout(dialog)
        layout.addWidget(muted("Edit existing scientific settings. Unknown advanced values are retained. Native output and boundaries remain the established production contract."))
        editor = QPlainTextEdit(yaml.safe_dump(self.session.configuration, sort_keys=False))
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            try:
                payload = yaml.safe_load(editor.toPlainText())
                self._apply_configuration(payload)
            except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
                self._error(str(exc))

    def _apply_configuration(self, payload):
        from avac_desktop.core.configuration import controlled_values, validate_controlled_values, REQUIRED_SECTIONS
        if not isinstance(payload, dict) or any(not isinstance(payload.get(key), dict) for key in REQUIRED_SECTIONS):
            raise ValueError("A complete AVAC YAML schema is required.")
        issues = validate_controlled_values(controlled_values(payload))
        if issues:
            raise ValueError("\n".join(issues))
        self.session.configuration = payload
        self.panels.refresh()
        self._configuration_changed()

    def load_yaml(self):
        if not self._can_replace():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Load complete AVAC configuration", "", "YAML (*.yaml *.yml)")
        if filename:
            try:
                self._apply_configuration(load_complete_configuration(filename))
            except ValueError as exc:
                self._error(str(exc))

    def save(self, checked=False, *, as_new=False) -> bool:
        if self.tasks.active or self.job.running:
            self._error("Finish the active task before saving the project.")
            return False
        if self.panels.timing_error:
            self._error(self.panels.timing_error)
            return False
        path = None if as_new else self.session.project_path
        if path is None:
            filename, _ = QFileDialog.getSaveFileName(self, "Save AVAC project", self.session.name+".avacproj", "AVAC project (*.avacproj)")
            if not filename:
                return False
            path = Path(filename)
            if path.suffix.lower() != ".avacproj":
                path = path.with_suffix(".avacproj")
        try:
            previous_workspace = self.session.workspace
            previous_results = self.session.selected_run, self.session.selected_wave
            save_project(self.session, path)
            self._busy(False)
            self._update_project()
            self._refresh_sampling_selectors()
            if (previous_workspace != self.session.workspace or
                    previous_results != (self.session.selected_run, self.session.selected_wave)):
                self._run_plan = None
                self._result_sources = {}
                self._gauge_cache_key = None
                if self.results:
                    root = self.session.selected_wave if self.session.analysis_kind in ("wave", "combined") else self.session.selected_run
                    self._load_results(self.session.analysis_kind, root, restore_selection=True)
            return True
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return False

    def _can_replace(self) -> bool:
        if self.job.running or self.tasks.active or self._video_export:
            self._error("A job is active. Stop it or wait before replacing this project or its inputs. Switching modes remains available.")
            return False
        return True

    def _confirm_unsaved(self) -> bool:
        if not self.session.dirty or (not self.session.terrain and not self.session.project_path):
            return True
        choice = QMessageBox.question(self, "Unsaved project", "Save project changes before continuing?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        return self.save() if choice == QMessageBox.Save else choice == QMessageBox.Discard

    def new_project(self):
        if self._can_replace() and self._confirm_unsaved():
            self._adopt(ProjectSession(configuration=default_configuration(), wave_setup=default_wave_setup()))

    def open_project(self):
        if not self._can_replace() or not self._confirm_unsaved():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Open AVAC project", "", "AVAC project (*.avacproj)")
        if filename:
            self.open_project_path(Path(filename))

    def open_project_path(self, path: Path):
        try:
            session, dem, provenance = load_project(path)
            self._adopt(session)
            if session.result_notice:
                self._append_log(session.result_notice)
            if dem:
                # Retain the manifest view before the map's first fit signal.
                extent = session.map_extent
                def restore():
                    self.data_loaded.disconnect(restore)
                    if extent:
                        self.map.restore_extent(extent)
                    if provenance.get("dem_sha256") and provenance["dem_sha256"] != self.session.terrain.source_hash:
                        self._error("Project terrain changed since save; preparation is stale.")
                    if provenance.get("release_sha256") and provenance["release_sha256"] != self.session.release_hash:
                        self._error("Project release polygons changed since save; preparation is stale.")
                    if self.session.analysis_kind in ("wave", "combined") and self.session.selected_wave:
                        QTimer.singleShot(0, lambda: self._load_results(self.session.analysis_kind, self.session.selected_wave, restore_selection=True))
                    elif self.session.selected_run:
                        QTimer.singleShot(0, lambda: self.load_run(self.session.selected_run, restore_selection=True))
                self.data_loaded.connect(restore)
                self.load_paths(dem, session.release_path, preserve_project_state=True)
            elif session.selected_wave and session.analysis_kind in ("wave", "combined"):
                self._load_results(session.analysis_kind, session.selected_wave, restore_selection=True)
            elif session.selected_run:
                self.load_run(session.selected_run, restore_selection=True)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self._error(str(exc))

    def _adopt(self, session):
        self.play_timer.stop()
        self.play.setText("Play")
        self.session = self.panels.session = session
        self.results, self.current_raster = None, None
        self._lake_rings = []
        self._dataset_identity = ""
        self._result_sources = {}
        self.current_variable, self.current_time = "terrain_elevation", None
        self.profile = self.gauge = None
        self._pending_initial_mesh = False
        self._initial_mesh = None
        self._initial_mesh_run = None
        self._pending_frame = False
        self._prepared_wave = None
        self._run_plan = None
        self._pipeline_active = False
        self._pipeline_snapshot = None
        self._gauge_cache_key = None
        self.map.clear()
        self._update_background_availability()
        self.map.time_text = ""
        self.map.styles = deepcopy(session.raster_styles)
        self.console.clear()
        self.chart.clear()
        self.gauge_chart.clear()
        self.chart.setTitle("")
        self.gauge_chart.setTitle("")
        self.slider.setRange(0, 0)
        self.time_label.setText("No completed run selected")
        self.variable.blockSignals(True)
        self.variable.clear()
        for key in ("depth", "velocity", "pressure", "snow_surface_elevation"):
            self.variable.addItem(LABELS[key], key)
        self.variable.blockSignals(False)
        self.run_button.setEnabled(False)
        self.run_button.setVisible(False)
        self.prepare_button.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Unconfigured")
        self.panels.run_info.setText("Validate inputs, inspect an initial-state preview, then prepare a new isolated run.")
        self.panels.analysis_info.setText("No completed run selected.")
        self.panels.wave_info.setText("No lake or WAVE scenario selected.")
        self.coordinate_label.setText("Import terrain to inspect coordinates and elevation.")
        self.panels.refresh()
        self.cpu.setValue(session.threads)
        self.wave_action.blockSignals(True)
        self.wave_action.setChecked(session.wave_enabled)
        self.wave_action.blockSignals(False)
        self._refresh_sampling_selectors()
        for key, checkbox in self.layer_checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(session.layers.get(key, key != "mesh"))
            checkbox.blockSignals(False)
        self.timeline.setEnabled(False)
        self.set_mode(session.mode)
        self._sync_dataset_selector()
        self._update_project()

    def _append_log(self, text: str):
        self.console.appendPlainText(text.rstrip())

    def _error(self, text: str):
        self.status_label.setText("Needs attention")
        self._append_log(text)
        self.bottom.setCurrentWidget(self.console)
        if self._console_collapsed:
            self.toggle_console()

    def _toggle_panels(self):
        visible = self.horizontal.widget(0).isVisible()
        self.horizontal.widget(0).setVisible(not visible)
        self.horizontal.widget(2).setVisible(not visible)

    def closeEvent(self, event):
        if self._video_export:
            self.stop()
            event.ignore()
            return
        if self.tasks.active:
            self._error("Cancel the data task or wait for it to finish before closing.")
            event.ignore()
            return
        if self.job.running:
            choice = QMessageBox.question(self, "Simulation running", "Stop this simulation before closing? Its partial output will remain marked cancelled.", QMessageBox.Yes | QMessageBox.Cancel)
            if choice != QMessageBox.Yes:
                event.ignore()
                return
            self.job.stop()
            event.ignore()
            self.job.state_changed.connect(lambda state: QTimer.singleShot(0, self.close) if state != "running" else None)
            return
        if self._confirm_unsaved():
            self.play_timer.stop()
            event.accept()
        else:
            event.ignore()

    def nativeEvent(self, event_type, message):
        hit = windows_resize_hit(self, event_type, message)
        return hit if hit is not None else super().nativeEvent(event_type, message)
