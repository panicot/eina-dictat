"""Captura de microfòn i neteja bàsica de l'àudio."""

from __future__ import annotations

import sys
import threading
import time

import numpy as np
import sounddevice as sd

TARGET_RATE = 16000


def resample_linear(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or data.size == 0:
        return data
    n_out = int(round(len(data) * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, data).astype(np.float32)


def trim_silence(data: np.ndarray, rate: int = TARGET_RATE) -> np.ndarray:
    """Retalla silenci inicial i final. Retorna buit si no hi ha veu."""
    if data.size == 0:
        return data
    peak = float(np.abs(data).max())
    if peak < 0.004:
        return data[:0]
    threshold = max(0.006, peak * 0.04)
    loud = np.flatnonzero(np.abs(data) > threshold)
    if loud.size == 0:
        return data[:0]
    start = max(0, int(loud[0]) - int(0.15 * rate))
    end = min(len(data), int(loud[-1]) + int(0.20 * rate))
    return data[start:end]


class Recorder:
    def __init__(self, samplerate: int = TARGET_RATE, device: str | None = None,
                 max_seconds: float = 60.0) -> None:
        self.requested_rate = samplerate
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        self.device = device or None
        self.max_seconds = max_seconds
        self.rate = samplerate
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._started_at = 0.0

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        try:
            sd.check_input_settings(device=self.device, channels=1,
                                    samplerate=self.requested_rate, dtype="float32")
            self.rate = self.requested_rate
        except Exception:  # noqa: BLE001
            info = sd.query_devices(self.device, kind="input")
            self.rate = int(info["default_samplerate"])

        with self._lock:
            self._chunks = []
        self._started_at = time.perf_counter()
        self._stream = sd.InputStream(
            samplerate=self.rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
            blocksize=0,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status and sys.stdout is not None:
            print(f"  [audio] {status}", flush=True)
        with self._lock:
            self._chunks.append(indata.copy())

    def stop(self) -> tuple[np.ndarray, float]:
        stream, self._stream = self._stream, None
        if stream is None:
            return np.zeros(0, dtype=np.float32), 0.0
        stream.stop()
        stream.close()

        with self._lock:
            chunks, self._chunks = self._chunks, []
        audio = (np.concatenate(chunks).reshape(-1) if chunks
                 else np.zeros(0, dtype=np.float32))
        audio = resample_linear(audio, self.rate, TARGET_RATE)
        audio = trim_silence(audio, TARGET_RATE)

        max_samples = int(self.max_seconds * TARGET_RATE)
        if audio.size > max_samples:
            audio = audio[:max_samples]

        return audio, audio.size / TARGET_RATE

    def cancel(self) -> None:
        self.stop()
