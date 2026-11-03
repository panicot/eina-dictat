"""Gestor de descàrregues de models de Hugging Face.

Cada descàrrega corre en un procés fill (`app.download_job`) per tal que
cancel·lar sigui immediat: es mata l'arbre de processos i s'atura la xarxa.
Els fitxers parcials queden a la memòria cau i la propera descàrrega reprèn.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from app.model_catalog import BY_REPO, repo_dir

ROOT = Path(__file__).resolve().parents[2]
CREATE_NO_WINDOW = 0x08000000


def _folder_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def _kill_process_tree(process: QProcess) -> None:
    pid = int(process.processId())
    if not pid:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=8,
            )
            return
        except Exception:  # noqa: BLE001
            pass
    process.kill()
    process.waitForFinished(1500)


class DownloadProcess(QProcess):
    def __init__(self, repo_id: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.repo_id = repo_id
        self.setProgram(sys.executable)
        self.setArguments(["-m", "app.download_job", repo_id])
        self.setWorkingDirectory(str(ROOT))
        self.setProcessChannelMode(QProcess.SeparateChannels)


class DownloadManager(QObject):
    """Una descàrrega activa i la resta en cua, per no saturar la xarxa."""

    progress = Signal(str, int, str, float, float)
    state_changed = Signal(str, str)
    finished = Signal(str)
    failed = Signal(str, str)
    cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: list[str] = []
        self._process: DownloadProcess | None = None
        self._active: str | None = None
        self._states: dict[str, str] = {}
        self._last_bytes = 0
        self._last_time = 0.0
        self._total_bytes = 0
        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._poll)

    # ------------------------------------------------------------------ query

    def state(self, repo_id: str) -> str:
        return self._states.get(repo_id, "idle")

    def is_busy(self, repo_id: str) -> bool:
        return self.state(repo_id) in {"queued", "downloading", "cancelling"}

    # -------------------------------------------------------------- lifecycle

    def enqueue(self, repo_id: str) -> None:
        if self.is_busy(repo_id):
            return
        if repo_id not in BY_REPO:
            self.failed.emit(repo_id, "Model desconegut")
            return
        self._states[repo_id] = "queued"
        self.state_changed.emit(repo_id, "queued")
        self._queue.append(repo_id)
        if self._active is None:
            self._start_next()

    def cancel(self, repo_id: str) -> None:
        if repo_id in self._queue:
            self._queue.remove(repo_id)
            self._states[repo_id] = "idle"
            self.state_changed.emit(repo_id, "idle")
            self.cancelled.emit(repo_id)
            return
        if self._active != repo_id or self._process is None:
            return
        self._states[repo_id] = "cancelling"
        self.state_changed.emit(repo_id, "cancelling")
        process, self._process = self._process, None
        try:
            process.finished.disconnect(self._on_finished)
            process.errorOccurred.disconnect(self._on_error)
        except (TypeError, RuntimeError):
            pass
        _kill_process_tree(process)
        process.deleteLater()
        self._finalize("cancelled")

    def shutdown(self) -> None:
        """Atura la descàrrega en curs sense esborrar els fitxers parcials."""
        if self._process is None:
            return
        process, self._process = self._process, None
        try:
            process.finished.disconnect(self._on_finished)
            process.errorOccurred.disconnect(self._on_error)
        except (TypeError, RuntimeError):
            pass
        _kill_process_tree(process)
        process.deleteLater()
        if self._active:
            self._states[self._active] = "idle"
        self._active = None
        self._queue.clear()
        self._timer.stop()

    def _start_next(self) -> None:
        if not self._queue:
            self._active = None
            return
        repo_id = self._queue.pop(0)
        info = BY_REPO.get(repo_id)
        self._active = repo_id
        self._states[repo_id] = "downloading"
        self._total_bytes = max(1, (info.size_mb if info else 1) * 1024 * 1024)
        self._last_bytes = _folder_size(repo_dir(repo_id))
        self._last_time = time.monotonic()
        self.state_changed.emit(repo_id, "downloading")

        process = DownloadProcess(repo_id, self)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        self._timer.start()
        process.start()

    # ----------------------------------------------------------------- signals

    def _poll(self) -> None:
        if self._active is None:
            return
        repo_id = self._active
        now = time.monotonic()
        received = _folder_size(repo_dir(repo_id))
        percent = int(min(99, received * 100 / self._total_bytes)) if self._total_bytes else 0
        elapsed = max(0.01, now - self._last_time)
        speed = max(0.0, (received - self._last_bytes) / elapsed)
        self._last_bytes = received
        self._last_time = now
        speed_text = f"{speed / (1024 * 1024):.1f} MB/s" if speed > 0 else "…"
        self.progress.emit(
            repo_id, percent, speed_text,
            received / (1024 * 1024), self._total_bytes / (1024 * 1024),
        )

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        process = self.sender()
        if process is not self._process or self._active is None:
            return
        repo_id = self._active
        if code == 0 and status == QProcess.NormalExit:
            self._states[repo_id] = "installed"
            self.progress.emit(repo_id, 100, "", 0.0, 0.0)
            self.finished.emit(repo_id)
            self._finalize("installed")
            return
        stderr = bytes(process.readAllStandardError()).decode("utf-8", "replace")
        message = stderr.strip().splitlines()[-1] if stderr.strip() else (
            f"El procés de descàrrega ha sortit amb codi {code}."
        )
        self._finalize("error", message)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if self.sender() is not self._process or self._active is None:
            return
        self._finalize("error", "No s'ha pogut iniciar la descàrrega.")

    def _finalize(self, result: str, message: str = "") -> None:
        repo_id = self._active
        self._timer.stop()
        self._process = None
        self._active = None
        if repo_id is None:
            self._start_next()
            return
        if result == "installed":
            self.state_changed.emit(repo_id, "installed")
        elif result == "cancelled":
            self._states[repo_id] = "idle"
            self.cancelled.emit(repo_id)
            self.state_changed.emit(repo_id, "idle")
        else:
            self._states[repo_id] = "error"
            self.failed.emit(repo_id, message)
            self.state_changed.emit(repo_id, "error")
        self._start_next()
