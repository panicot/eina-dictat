#!/usr/bin/env python3
"""CustormWispeFlow - dictat local per veu.

Prem la tecla configurada (F8 per defecte), parla i torna a prémer per inserir el
text al camp que tingui el focus.

Hotkeys:
  F8                comencar / aturar (o mantenir, segons config)
  Ctrl+Shift+1/2/3  canviar a catala / castella / angles
  Ctrl+Shift+Q      sortir
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app import __version__  # noqa: E402
from app.audio import Recorder  # noqa: E402
from app.config import ROOT, Config, load  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.feedback import LANGUAGE_EVENTS, Event, Feedback  # noqa: E402
from app.history import trim_history  # noqa: E402
from app.hotkeys import HotkeyManager  # noqa: E402
from app.insert import InsertAborted, insert  # noqa: E402
from app.instance import SingleInstance  # noqa: E402
from app.logs import get_logger, setup_logging  # noqa: E402
from app.state import State, modes_label, status_line  # noqa: E402
from app.textmodes import TextModes  # noqa: E402
from app.undo import LastInsert, Undoer, get_foreground_window  # noqa: E402


class DictationApp:
    def __init__(self, cfg: Config, demo: str | None = None,
                 dry_run: bool = False, punct: bool = False,
                 spell: bool = False, save_history: bool = True,
                 quiet: bool = False,
                 on_state: Callable[[State], None] | None = None,
                 on_status: Callable[[str], None] | None = None,
                 on_transcript: Callable[[dict], None] | None = None,
                 on_error: Callable[[str], None] | None = None,
                 on_language: Callable[[str], None] | None = None,
                 on_undo: Callable[[bool, str], None] | None = None,
                 on_quit: Callable[[], None] | None = None) -> None:
        self.cfg = cfg
        self.engine = Engine(cfg)
        self.engine.on_status = self._status
        self.recorder = Recorder(device=cfg.device, max_seconds=cfg.max_seconds)
        self.modes = TextModes(cfg)
        self.modes.punctuation_mode = punct
        self.modes.spelling_mode = spell
        self.demo = Path(demo) if demo else None
        self.dry_run = dry_run
        self.save_history = save_history
        self.log = get_logger()
        self.language = cfg.language
        self.busy = False
        self._last_toggle = 0.0
        self._stop_event = threading.Event()
        self.hotkeys = HotkeyManager()
        self.history = ROOT / "history.jsonl"
        self.feedback = Feedback(enabled=cfg.beeps)
        self.state = State.IDLE
        self._state_lock = threading.Lock()
        self._print_lock = threading.Lock()
        self.last_insert: LastInsert | None = None
        self.undoer = Undoer()
        self.quiet = quiet
        self.on_state = on_state or (lambda state: None)
        self.on_status = on_status or (lambda message: None)
        self.on_transcript = on_transcript or (lambda payload: None)
        self.on_error = on_error or (lambda message: None)
        self.on_language = on_language or (lambda language: None)
        self.on_undo = on_undo or (lambda ok, message: None)
        self.on_quit = on_quit

    # ---------- utilitats ----------

    def _say(self, message: str) -> None:
        if not self.quiet:
            print(message, flush=True)

    def _status(self, message: str) -> None:
        if not self.quiet:
            print(f"  · {message}", flush=True)
        self.on_status(message)

    def _print_status(self) -> None:
        if self.quiet:
            return
        line = status_line(
            self.state, self.language,
            self.modes.punctuation_mode, self.modes.spelling_mode,
        )
        with self._print_lock:
            print(line, flush=True)

    def _set_state(self, state: State) -> None:
        with self._state_lock:
            changed = state != self.state
            self.state = state
        if changed:
            self._print_status()
            self.log.info(
                "state %s lang=%s modes=%s", state.value, self.language,
                modes_label(self.modes.punctuation_mode,
                            self.modes.spelling_mode),
            )
            self.on_state(state)

    @staticmethod
    def _mode_event(name: str) -> Event | None:
        if name == "signes de puntuacio ON":
            return Event.PUNCT_ON
        if name == "signes de puntuacio OFF":
            return Event.PUNCT_OFF
        if name == "deletreig ON":
            return Event.SPELL_ON
        if name == "deletreig OFF":
            return Event.SPELL_OFF
        if name == "mode normal":
            return Event.MODE_NORMAL
        return None

    def _save_history(self, language: str, text: str, duration: float,
                      latency: float, method: str) -> None:
        if not self.save_history:
            return
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "language": language,
            "duration_s": round(duration, 2),
            "latency_s": round(latency, 2),
            "chars": len(text),
            "method": method,
            "text": text,
        }
        with self.history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ---------- flux de dictat ----------

    def start(self) -> None:
        if self.busy or self.recorder.is_recording:
            return
        try:
            self.recorder.start()
        except Exception as exc:  # noqa: BLE001
            self._say(f"No s'ha pogut obrir el microfon: {exc}")
            self.log.error("microphone: %s", exc)
            self._set_state(State.ERROR)
            self.feedback.play(Event.ERROR)
            self.on_error(f"No s'ha pogut obrir el micròfon: {exc}")
            return
        self._say("Escoltant... (torna a prémer per aturar)")
        self._set_state(State.LISTENING)
        self.feedback.play(Event.LISTENING)

    def stop(self) -> None:
        if not self.recorder.is_recording:
            return
        audio, duration = self.recorder.stop()
        if duration < 0.4:
            self._say("Massa curt, no s'ha transcrit res.")
            self._status("Massa curt, no s'ha transcrit res.")
            self._set_state(State.IDLE)
            self.feedback.play(Event.NO_SPEECH)
            return
        self.busy = True
        self._set_state(State.TRANSCRIBING)
        self.feedback.play(Event.PROCESSING)
        threading.Thread(target=self._process, args=(audio, duration),
                         daemon=True).start()

    def toggle(self) -> None:
        now = time.monotonic()
        if now - self._last_toggle < 0.35:
            return
        self._last_toggle = now
        if self.busy:
            self._say("Encara estic transcrivint...")
            self._status("Encara estic transcrivint...")
            self.feedback.play(Event.BUSY)
            return
        if self.demo is not None:
            self.busy = True
            self._set_state(State.TRANSCRIBING)
            self.feedback.play(Event.PROCESSING)
            threading.Thread(target=self._process_demo, daemon=True).start()
            return
        if self.recorder.is_recording:
            self.stop()
        else:
            self.start()

    def _process_demo(self) -> None:
        started = time.perf_counter()
        try:
            text, probability = self.engine.transcribe_file(self.demo, self.language)
            latency = time.perf_counter() - started
            self._deliver(self.language, text, 0.0, latency, probability)
        except Exception as exc:  # noqa: BLE001
            self._say(f"ERROR: {exc}")
            self.log.exception("transcription failed")
            self._set_state(State.ERROR)
            self.feedback.play(Event.ERROR)
            self.on_error(f"No s'ha pogut transcriure: {exc}")
        finally:
            self.busy = False
            if self.state != State.ERROR:
                self._set_state(State.IDLE)

    def _deliver(self, language: str, text: str, duration: float,
                 latency: float, probability: float) -> None:
        text = self.modes.transform(text)
        events = list(self.modes.events)
        for event in events:
            self._say(f"  · {event}")
            self.log.info("mode event=%s", event)
            sound = self._mode_event(event)
            if sound is not None:
                self.feedback.play(sound)
        if not text:
            if not events:
                self._say("No s'ha detectat parla.")
                self.log.info("no speech lang=%s", language)
                self.feedback.play(Event.NO_SPEECH)
                self.on_status("No s'ha detectat parla.")
            return
        hwnd = get_foreground_window()
        if self.dry_run:
            chars, method = len(text), "dry-run"
        else:
            try:
                chars, method = insert(
                    text,
                    mode=self.cfg.insert_mode,
                    threshold=self.cfg.paste_threshold,
                    restore_clipboard=self.cfg.restore_clipboard,
                    expected_hwnd=hwnd,
                )
            except InsertAborted as exc:
                message = ("Inserció interrompuda: has canviat de finestra "
                           f"({exc.chars_written} caràcters escrits).")
                self._say(message)
                if exc.chars_written:
                    self._say("Torna a la finestra i prem F9 per desfer el que "
                              "s'ha escrit.")
                    self.last_insert = LastInsert(
                        text=text, method="type", hwnd=hwnd,
                        chars=exc.chars_written,
                    )
                self.log.warning("insert aborted chars=%d", exc.chars_written)
                self._set_state(State.ERROR)
                self.feedback.play(Event.ERROR)
                self.on_error(message)
                return
            self.last_insert = LastInsert(
                text=text, method=method, hwnd=hwnd, chars=chars,
            )
        self._say(f"[{language}] {latency:.2f}s | {chars} car. | {method} | "
                  f"conf {probability:.2f}")
        self._say(f"  > {text}")
        self._save_history(language, text, duration, latency, method)
        self.log.info(
            "deliver lang=%s chars=%d method=%s latency=%.2f conf=%.2f",
            language, chars, method, latency, probability,
        )
        self.feedback.play(Event.DONE)
        self.on_transcript({
            "language": language,
            "chars": chars,
            "method": method,
            "latency": latency,
            "duration": duration,
            "probability": probability,
            "text": text,
        })

    def _process(self, audio, duration: float) -> None:  # noqa: ANN001
        language = self.language
        started = time.perf_counter()
        try:
            text, probability = self.engine.transcribe(audio, language)
            latency = time.perf_counter() - started
            self._deliver(language, text, duration, latency, probability)
        except Exception as exc:  # noqa: BLE001
            self._say(f"ERROR: {exc}")
            self.log.exception("transcription failed")
            self._set_state(State.ERROR)
            self.feedback.play(Event.ERROR)
            self.on_error(f"No s'ha pogut transcriure: {exc}")
        finally:
            self.busy = False
            if self.state != State.ERROR:
                self._set_state(State.IDLE)

    # ---------- desfer ----------

    def undo(self) -> None:
        if self.busy:
            self._say("Encara estic transcrivint...")
            self._status("Encara estic transcrivint...")
            self.feedback.play(Event.BUSY)
            self.on_undo(False, "Encara estic transcrivint...")
            return
        ok, message = self.undoer.undo(self.last_insert)
        self._say(message)
        self.log.info("undo ok=%s message=%s", ok, message)
        if ok:
            self.last_insert = None
            self.feedback.play(Event.UNDONE)
        else:
            self.feedback.play(Event.ERROR)
        self.on_undo(ok, message)

    # ---------- idioma ----------

    def set_language(self, language: str) -> None:
        if language not in self.cfg.models:
            return
        self.language = language
        self._say(f"Idioma: {language.upper()}")
        self.log.info("language %s", language)
        self._print_status()
        self.feedback.play(LANGUAGE_EVENTS[language])
        self.on_language(language)
        threading.Thread(target=self._preload, args=(language,), daemon=True).start()

    def _preload(self, language: str) -> None:
        try:
            self.engine.preload(language)
        except Exception as exc:  # noqa: BLE001
            message = f"No s'ha pogut carregar el model per a {language}: {exc}"
            self._say(message)
            try:
                self.on_error(message)
            except Exception:  # noqa: BLE001
                pass

    # ---------- arrencada ----------

    def _register_hotkeys(self) -> None:
        if self.cfg.mode == "hold":
            self.hotkeys.add(self.cfg.hotkey, self.start, self.stop)
        else:
            self.hotkeys.add(self.cfg.hotkey, self.toggle)

        self.hotkeys.add(self.cfg.undo_hotkey, self.undo)

        for language, combo in (("ca", "ctrl+shift+1"), ("es", "ctrl+shift+2"),
                                ("en", "ctrl+shift+3")):
            self.hotkeys.add(combo, lambda l=language: self.set_language(l))
        self.hotkeys.add("ctrl+shift+q", self.quit)

    def _start_hotkeys(self) -> bool:
        try:
            self.hotkeys.start()
            return True
        except Exception as exc:  # noqa: BLE001
            message = f"No s'han pogut activar els hotkeys: {exc}"
            self._say(message)
            self.log.error("hotkeys: %s", exc)
            self.on_error(message)
            return False

    def start_services(self) -> None:
        """Arrenca hotkeys i carrega el model sense bloquejar la interfície."""
        self.log.info("start version=%s lang=%s model=%s", __version__,
                      self.language, self.cfg.model_for(self.language))
        removed = trim_history(self.history, self.cfg.history_max_lines)
        if removed:
            self._say(f"Historial retallat: {removed} linies antigues.")
            self.log.info("history trimmed removed=%d", removed)
        self._register_hotkeys()
        self._start_hotkeys()
        threading.Thread(target=self._preload, args=(self.language,),
                         daemon=True).start()

    def run(self) -> None:
        print(f"CustormWispeFlow {__version__}")
        self.log.info("start version=%s lang=%s model=%s", __version__,
                      self.language, self.cfg.model_for(self.language))
        removed = trim_history(self.history, self.cfg.history_max_lines)
        if removed:
            print(f"Historial retallat: {removed} linies antigues.", flush=True)
            self.log.info("history trimmed removed=%d", removed)
        print(f"Idioma inicial: {self.language.upper()}  |  "
              f"Model: {self.cfg.model_for(self.language)}")
        if self.demo:
            print(f"Mode demo: {self.demo} (F8 transcriu aquest fitxer)")
        print("Carregant model...", flush=True)
        self.engine.preload(self.language)

        self._register_hotkeys()
        self._start_hotkeys()

        if self.cfg.mode == "hold":
            mode_text = f"mantenir {self.cfg.hotkey.upper()}"
        else:
            mode_text = f"prémer {self.cfg.hotkey.upper()}"
        print()
        print(f"A punt. {mode_text} per dictar.")
        print(f"Ctrl+Shift+1/2/3 = catala/castella/angles | "
              f"{self.cfg.undo_hotkey.upper()} = desfer | Ctrl+Shift+Q = sortir")
        print("Veu: 'signes de puntuacio' | 'lletra a lletra' | 'mode normal'")
        self._print_status()
        print("Ves a qualsevol camp de text i dicta.", flush=True)
        try:
            self._stop_event.wait()
        except KeyboardInterrupt:
            self.quit()

    def apply_config(self, new_cfg: Config) -> None:
        """Aplica en calent els canvis fets a la finestra de configuració."""
        old = self.cfg
        device_changed = ((old.device or None) != (new_cfg.device or None)
                          or old.max_seconds != new_cfg.max_seconds)
        hotkeys_changed = (
            (old.hotkey, old.mode, old.undo_hotkey)
            != (new_cfg.hotkey, new_cfg.mode, new_cfg.undo_hotkey)
        )
        models_changed = old.models != new_cfg.models

        self.cfg = new_cfg
        self.engine.reload_config(new_cfg)
        punctuation = self.modes.punctuation_mode
        spelling = self.modes.spelling_mode
        self.modes = TextModes(new_cfg)
        self.modes.punctuation_mode = punctuation
        self.modes.spelling_mode = spelling
        self.feedback.enabled = new_cfg.beeps

        if device_changed:
            was_recording = self.recorder.is_recording
            if was_recording:
                self.recorder.cancel()
            self.recorder = Recorder(device=new_cfg.device,
                                     max_seconds=new_cfg.max_seconds)
            if was_recording:
                self._set_state(State.IDLE)

        if hotkeys_changed:
            self.hotkeys.stop()
            self.hotkeys = HotkeyManager()
            self._register_hotkeys()
            self._start_hotkeys()

        if self.language not in new_cfg.models:
            self.language = new_cfg.language
            self.on_language(self.language)

        if models_changed:
            threading.Thread(target=self._preload, args=(self.language,),
                             daemon=True).start()

        self.log.info(
            "config applied hotkey=%s mode=%s device=%s models=%s",
            new_cfg.hotkey, new_cfg.mode, new_cfg.device or "default",
            new_cfg.models,
        )

    def shutdown(self) -> None:
        self._stop_event.set()
        self.hotkeys.stop()
        self.feedback.close()
        try:
            self.recorder.cancel()
        except Exception:  # noqa: BLE001
            pass

    def quit(self) -> None:
        if self.on_quit is not None:
            self.on_quit()
            return
        self._say("\nFins aviat.")
        self.shutdown()
        os._exit(0)


def list_devices() -> None:
    import sounddevice as sd

    print(sd.query_devices())


def main() -> int:
    parser = argparse.ArgumentParser(description="Dictat local per veu")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--language", choices=["ca", "es", "en"], default=None)
    parser.add_argument("--model", default=None,
                        help="forca aquest model per a tots els idiomes")
    parser.add_argument("--file", default=None,
                        help="transcriu un fitxer d'audio i surt")
    parser.add_argument("--demo", default=None,
                        help="amb hotkeys: F8 transcriu aquest fitxer en lloc del microfon")
    parser.add_argument("--dry-run", action="store_true",
                        help="no insereix el text, nomes el mostra")
    parser.add_argument("--insert", action="store_true",
                        help="amb --file, insereix el text al camp actiu")
    parser.add_argument("--punct", action="store_true",
                        help="comenca amb signes de puntuacio activats")
    parser.add_argument("--spell", action="store_true",
                        help="comenca amb deletreig explicit activat")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--no-beep", action="store_true")
    parser.add_argument("--no-history", action="store_true",
                        help="no escriu history.jsonl")
    parser.add_argument("--verbose", action="store_true",
                        help="mostra el log tambe a la consola")
    parser.add_argument("--allow-multiple", action="store_true",
                        help="permet una segona instancia (nomes per provar)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return 0

    cfg = load(args.config)
    if args.language:
        cfg.language = args.language
    if args.model:
        cfg.models = {key: args.model for key in cfg.models}
    if args.no_beep:
        cfg.beeps = False

    logger = setup_logging(ROOT / "logs", verbose=args.verbose)
    logger.info(
        "config hotkey=%s undo_hotkey=%s lang=%s insert_mode=%s beeps=%s "
        "history=%s history_max_lines=%d",
        cfg.hotkey, cfg.undo_hotkey, cfg.language, cfg.insert_mode,
        cfg.beeps, not args.no_history, cfg.history_max_lines,
    )

    if args.file:
        engine = Engine(cfg)
        engine.on_status = lambda message: print(f"  · {message}", flush=True)
        started = time.perf_counter()
        text, probability = engine.transcribe_file(args.file, cfg.language)
        elapsed = time.perf_counter() - started
        modes = TextModes(cfg)
        modes.punctuation_mode = args.punct
        modes.spelling_mode = args.spell
        text = modes.transform(text)
        print(f"[{cfg.language}] {elapsed:.2f}s | conf {probability:.2f}")
        for event in modes.events:
            print(f"  · {event}")
        print(text)
        logger.info(
            "file path=%s lang=%s elapsed=%.2f conf=%.2f chars=%d",
            args.file, cfg.language, elapsed, probability, len(text),
        )
        if args.insert and text:
            chars, method = insert(text, cfg.insert_mode, cfg.paste_threshold,
                                   cfg.restore_clipboard)
            print(f"Inserits {chars} caracters ({method}).")
        return 0

    instance: SingleInstance | None = None
    if not args.allow_multiple:
        instance = SingleInstance()
        if instance.already_running:
            instance.close()
            print("Ja hi ha una instancia de CustormWispeFlow en marxa.", flush=True)
            print("Tanca-la, o fes servir --allow-multiple si estas provant.",
                  flush=True)
            return 1

    try:
        DictationApp(cfg, demo=args.demo, dry_run=args.dry_run,
                     punct=args.punct, spell=args.spell,
                     save_history=not args.no_history).run()
    finally:
        if instance is not None:
            instance.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
