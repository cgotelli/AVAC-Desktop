"""Persistent PySide6 owner of one verified direct native solver process."""
from __future__ import annotations

import os
from pathlib import Path
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
import yaml

from avac_desktop.core.run_diagnostics import solver_failure_reason, write_volume_balance
from avac_desktop.core.run_project import read_run_metadata, update_run_status


class NativeJob(QObject):
    log = Signal(str)
    state_changed = Signal(str)
    progress = Signal(int, int)
    completed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._stdout)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._progress)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.process.kill)
        self.root: Path | None = None
        self.state = "ready"
        self.expected = 0
        self.expected_fgout = 0
        self.cancel_requested = False
        self.tail = ""
        self.fatal: str | None = None
        self.log_file = None
        self.started_at = 0.
        self.kind = "AVAC"
        self.output: Path | None = None

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    def start(self, root: Path, solver: Path, threads: int, *, kind="AVAC") -> None:
        if self.running:
            raise ValueError("A simulation is already running.")
        import json
        if kind not in ("AVAC", "WAVE"):
            raise ValueError("Unsupported native job type.")
        self.kind = kind
        metadata = read_run_metadata(root) if kind == "AVAC" else json.loads((root/".avac_qgis_wave_run.json").read_text(encoding="utf-8"))
        if metadata.get("status") != "prepared":
            raise ValueError("Run is not in an unstarted prepared state.")
        output = root/("AVAC" if kind == "AVAC" else "Wave")/"_output"
        self.output = output
        if not output.is_dir() or not any(output.glob("*.data")):
            raise ValueError("Native input controls are not staged.")
        config_path = root/"AVAC"/"AVAC_configuration.yaml" if kind == "AVAC" else root/"impulse_configuration.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.expected = int(config["computation"]["nb_simul"])+1
        self.expected_fgout = int(config["animation"]["n_out"]) if kind == "AVAC" else self.expected
        self.root, self.cancel_requested, self.tail, self.fatal = root, False, "", None
        environment = QProcessEnvironment.systemEnvironment()
        for key in ("CLAW", "CLAW_PYTHON", "FC", "PYTHONPATH", "AVAC_INITIAL_MESH_ONLY"):
            environment.remove(key)
        runtime = Path(metadata["runtime"])
        environment.insert("OMP_NUM_THREADS", str(threads))
        environment.insert("PATH", os.pathsep.join((str(runtime/"bin"), str(runtime/"lib"), environment.value("PATH"))))
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(output))
        self.process.setProgram(str(solver))
        self.process.setArguments([])
        self.log_file = (root/"desktop_solver.log").open("a", encoding="utf-8")
        self.started_at = time.monotonic()
        self._update_status("running", omp_threads=threads)
        self._state("running")
        self.log.emit(f"Starting {solver}\nOMP_NUM_THREADS={threads}\nRun: {root}\n")
        self.process.start()
        self.timer.start()

    def stop(self) -> None:
        if self.running:
            self.cancel_requested = True
            # Direct xgeoclaw is the QProcess child, with no Make/shell tree.
            # Stop exactly this owned native process; no process-name searches.
            self.process.terminate()
            self.kill_timer.start(3000)

    def _state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    def _record(self, text: str) -> None:
        combined = self.tail + text
        self.fatal = self.fatal or solver_failure_reason(combined)
        self.tail = combined[-8192:]
        if self.log_file:
            self.log_file.write(text)
            self.log_file.flush()
        self.log.emit(text)

    def _stdout(self) -> None:
        self._record(bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace"))

    def _stderr(self) -> None:
        self._record(bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace"))

    def _progress(self) -> None:
        if self.root:
            count = len(list(self.output.glob("fort.t*")))
            self.progress.emit(count, self.expected)

    def _error(self, error) -> None:
        if error == QProcess.FailedToStart:
            self._record(f"Native executable failed to start: {self.process.errorString()}\n")
            self._finish_state("failed", error=self.process.errorString())

    def _finished(self, code: int, exit_status) -> None:
        self._stdout()
        self._stderr()
        if self.cancel_requested:
            state = "cancelled"
        elif code or exit_status != QProcess.NormalExit or self.fatal:
            state = "failed"
        else:
            output = self.output
            fort_count = len(list(output.glob("fort.t*")))
            fgout_count = len(list(output.glob("fgout0001.t*")))
            state = "completed" if fort_count == self.expected and fgout_count == self.expected_fgout else "failed"
            if state == "failed":
                self._record(f"Incomplete output: native frames {fort_count}/{self.expected}, fixed-grid frames {fgout_count}/{self.expected_fgout}\n")
        self._finish_state(state, exit_code=code, solver_failure=self.fatal)

    def _finish_state(self, state: str, **fields) -> None:
        self.timer.stop()
        self.kill_timer.stop()
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self._update_status(state, elapsed_seconds=time.monotonic()-self.started_at, **fields)
        if state == "completed" and self.kind == "AVAC":
            try:
                diagnostics = write_volume_balance(self.root/"AVAC"/"_output")
                if diagnostics:
                    self.log.emit(f"Volume diagnostics: {diagnostics}\n")
            except (ValueError, OSError) as exc:
                self.log.emit(f"Volume diagnostics unavailable: {exc}\n")
        self._state(state)
        self.log.emit(f"Run {state}: {self.root}\n")
        if state == "completed":
            self.completed.emit(self.root)

    def _update_status(self, status, **fields):
        if self.kind == "AVAC":
            update_run_status(self.root/"AVAC", status, **fields)
        else:
            from .wave import update_status
            update_status(self.root, status, **fields)
