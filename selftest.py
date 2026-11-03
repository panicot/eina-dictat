#!/usr/bin/env python3
"""Proves automatiques de l'MVP: motor de transcripcio i insercio de text.

Us:
  python selftest.py                 # totes les proves
  python selftest.py --skip-engine   # nomes insercio
  python selftest.py --skip-insert   # nomes motor
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent


def test_engine(config_path: Path | None) -> bool:
    from app.config import load
    from app.engine import Engine

    sample = ROOT / "samples" / "ca_01.wav"
    if not sample.exists():
        print("Saltant motor: falta samples/ca_01.wav (executa make_samples.py).")
        return True

    cfg = load(config_path)
    engine = Engine(cfg)
    engine.on_status = lambda message: print(f"  · {message}", flush=True)
    print(f"Motor: {cfg.model_for('ca')}")
    started = time.perf_counter()
    text, probability = engine.transcribe_file(sample, "ca")
    elapsed = time.perf_counter() - started
    print(f"  temps: {elapsed:.2f}s  conf: {probability:.2f}")
    print(f"  text : {text}")
    ok = len(text) > 10
    print(f"  resultat: {'OK' if ok else 'FALLA'}\n")
    return ok


def test_insert() -> bool:
    import ctypes
    import tkinter as tk

    from app.insert import InsertAborted, paste_text, send_backspaces, type_text

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    GA_ROOT = 2

    def top_level(hwnd: int) -> int:
        return user32.GetAncestor(hwnd, GA_ROOT) or hwnd

    def foreground_title() -> str:
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 256)
        return buffer.value

    def force_foreground(hwnd: int) -> None:
        """Windows no deixa robar el focus a qualsevol proces; adjuntant-nos al
        fil de la finestra activa sí que podem portar la nostra al davant."""
        own = top_level(hwnd)
        current = user32.GetForegroundWindow()
        if not current or top_level(current) == own:
            return
        other_thread = user32.GetWindowThreadProcessId(current, None)
        own_thread = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(own_thread, other_thread, True)
        try:
            user32.BringWindowToTop(own)
            user32.SetForegroundWindow(own)
            user32.SetFocus(own)
        finally:
            user32.AttachThreadInput(own_thread, other_thread, False)

    root = tk.Tk()
    root.title("CustormWispeFlow - test d'insercio")
    root.geometry("700x240+200+200")
    root.attributes("-topmost", True)
    widget = tk.Text(root, height=7, width=78)
    widget.pack(padx=12, pady=12)
    label = tk.Label(root, text="Esperant...")
    label.pack()
    window_handle: dict[str, int] = {}

    typed_expected = "Hola, prova d'insercio 123.\nSegona linia: à è í ò ú ç."
    pasted_expected = "Aixo ve del porta-retalls."
    results: dict[str, str] = {}
    verdict: dict[str, bool] = {"ok": False, "skipped": False}
    aborted: list[str] = []

    def type_guarded(text: str, hwnd: int) -> None:
        try:
            type_text(text, expected_hwnd=hwnd)
        except InsertAborted as exc:
            aborted.append(f"type:{exc.chars_written}")

    def paste_guarded(text: str, hwnd: int) -> None:
        try:
            paste_text(text, True, expected_hwnd=hwnd)
        except InsertAborted as exc:
            aborted.append(f"paste:{exc.chars_written}")

    def has_focus() -> bool:
        own = window_handle.get("hwnd")
        if not own:
            return False
        current = user32.GetForegroundWindow()
        return bool(current) and top_level(current) == top_level(own)

    def run_async(function, *args) -> None:
        # Fora del fil de Tk: si bloquegem el mainloop, l'app no pot processar
        # el Ctrl+V fins que ja hem restaurat el porta-retalls.
        threading.Thread(target=function, args=args, daemon=True).start()

    def skip(reason: str) -> None:
        # Mai no enviem keystrokes a una finestra aliena: si no tenim el focus,
        # saltem la prova en lloc d'escriure a l'atzar.
        print(f"  AVIS: {reason}")
        print(f"  Finestra activa: {foreground_title()!r}")
        print("  Prova d'insercio saltada (no s'ha enviat cap tecla).")
        verdict["ok"] = True
        verdict["skipped"] = True
        root.after(200, root.destroy)

    def focus(attempt: int = 0) -> None:
        window_handle["hwnd"] = root.winfo_id()
        window_handle["top"] = top_level(window_handle["hwnd"])
        force_foreground(window_handle["hwnd"])
        root.lift()
        root.focus_force()
        widget.focus_force()
        if not has_focus():
            if attempt < 12:
                root.after(300, lambda: focus(attempt + 1))
            else:
                skip("una altra aplicacio te el focus i no el podem recuperar.")
            return
        label.config(text="Escrivint amb SendInput...")
        root.after(700, do_type)

    def do_type() -> None:
        force_foreground(window_handle["hwnd"])
        root.focus_force()
        widget.focus_force()
        if not has_focus():
            skip("s'ha perdut el focus abans d'escriure.")
            return
        run_async(type_guarded, typed_expected, window_handle["top"])
        root.after(1200, check_type)

    def check_type() -> None:
        results["typed"] = widget.get("1.0", "end-1c")
        if aborted:
            skip(f"la finestra ha canviat durant la insercio ({aborted[-1]}).")
            return
        if not has_focus():
            skip("s'ha perdut el focus abans de desfer.")
            return
        label.config(text="Desfent amb retrocessos...")
        run_async(send_backspaces, len(typed_expected))
        root.after(900, check_undo)

    def check_undo() -> None:
        results["undone"] = widget.get("1.0", "end-1c")
        widget.focus_force()
        label.config(text="Enganxant amb el porta-retalls...")
        root.after(500, do_paste)

    def do_paste() -> None:
        force_foreground(window_handle["hwnd"])
        root.focus_force()
        widget.focus_force()
        if not has_focus():
            skip("s'ha perdut el focus abans d'enganxar.")
            return
        run_async(paste_guarded, pasted_expected, window_handle["top"])
        root.after(1200, finish)

    def finish() -> None:
        results["pasted"] = widget.get("1.0", "end-1c")
        if any(item.startswith("paste:") for item in aborted):
            skip(f"la finestra ha canviat durant l'enganxament ({aborted[-1]}).")
            return
        print("TYPE :", repr(results.get("typed")))
        print("UNDO :", repr(results.get("undone")))
        print("PASTE:", repr(results.get("pasted")))
        ok_type = "prova d'insercio 123" in results.get("typed", "")
        ok_accents = "à è í ò ú ç" in results.get("typed", "")
        ok_undo = results.get("undone") == ""
        ok_paste = "porta-retalls" in results.get("pasted", "")
        verdict["ok"] = ok_type and ok_accents and ok_undo and ok_paste
        print(f"  resultat: {'OK' if verdict['ok'] else 'FALLA'}\n")
        root.after(200, root.destroy)

    root.after(600, focus)
    root.mainloop()
    return verdict["ok"]


def test_text_modes(config_path: Path | None) -> bool:
    from app.config import load
    from app.textmodes import TextModes

    cfg = load(config_path)
    modes = TextModes(cfg)
    checks: list[tuple[str, str, str]] = []
    failures = 0

    def check(label: str, got: str, expected: str) -> None:
        nonlocal failures
        ok = got == expected
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}  ({got!r})")
        checks.append((label, got, expected))

    print("Modes de veu:")
    check("deletreig automatic", modes.transform("u erre ele"), "URL")
    check("lletres ja separades", modes.transform("S C F F"), "SCFF")
    check("una lletra sola", modes.transform("efa"), "F")
    check("nom ambigu intacte", modes.transform("ca"), "ca")
    check("paraules curtes intactes", modes.transform("la a i la o"),
          "la a i la o")
    check("mode normal no toca res", modes.transform("punt"), "punt")

    out = modes.transform("signes de puntuacio.")
    check("activar puntuacio", out, "")
    check("puntuacio activa", str(modes.punctuation_mode), "True")
    check("URL dictada", modes.transform("example punt com barra documents"),
          "example.com/documents")
    check("signe solt", modes.transform("punt i coma"), ";")
    check("barra invertida", modes.transform("barra invertida"), "\\")

    out = modes.transform("fi signes de puntuacio.")
    check("desactivar puntuacio", out, "")
    check("puntuacio desactivada", str(modes.punctuation_mode), "False")
    check("punt sense mode", modes.transform("punt"), "punt")

    out = modes.transform("lletra a lletra")
    check("activar deletreig", out, "")
    check("deletreig explicit", modes.transform("a be ce"), "ABC")
    check("deletreig angles", modes.transform("double u why zed"), "WYZ")
    out = modes.transform("fi mode lletres")
    check("desactivar deletreig", out, "")
    check("una lletra sense mode", modes.transform("a"), "a")
    check("frase 'la lletra X'", modes.transform("Escriu la lletra essa."),
          "Escriu la lletra S.")
    check("frase amb ompliment", modes.transform("Escriu la lletra, a, essa."),
          "Escriu la lletra S.")
    check("dues frases de lletra", modes.transform("la lletra essa i la lletra u"),
          "la lletra S i la lletra U")
    check("lletra ja escrita", modes.transform("Escriu la lletra S, i la, lletra, a."),
          "Escriu la lletra S, i la, lletra A.")
    check("lletra ja escrita amb sigles",
          modes.transform("Escriu la lletra A, i les sigles, URL."),
          "Escriu la lletra A, i les sigles, URL.")
    check("frase de lletra intacta", modes.transform("la lletra és gran"),
          "la lletra és gran")

    fuzzy = TextModes(cfg)
    out = fuzzy.transform("Sínnes de puntuació. hola punt")
    check("variant de l'ordre", out, "hola.")
    check("variant activa el mode", str(fuzzy.punctuation_mode), "True")
    out = fuzzy.transform("Fi Sínnes de puntuació. hola punt")
    check("variant de desactivar", out, "hola punt")
    check("variant desactiva el mode", str(fuzzy.punctuation_mode), "False")

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def test_feedback() -> bool:
    from app.feedback import Event, Feedback, pattern_for

    print("Senyals sonors:")
    failures = 0

    def check(label: str, ok: bool) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}")

    check("tots els estats tenen patro",
          all(len(pattern_for(event)) > 0 for event in Event))
    patterns = [pattern_for(event) for event in Event]
    check("patrons distints", len(set(patterns)) == len(patterns))
    check("activar i desactivar son inversos",
          pattern_for(Event.PUNCT_ON) == tuple(reversed(pattern_for(Event.PUNCT_OFF)))
          and pattern_for(Event.SPELL_ON) == tuple(reversed(pattern_for(Event.SPELL_OFF))))

    calls: list[tuple[int, int]] = []
    feedback = Feedback(enabled=True, player=lambda f, d: calls.append((f, d)))
    feedback.play(Event.PUNCT_ON)
    feedback.play(Event.DONE)
    idle = feedback.wait_idle(2.0)
    feedback.close()
    expected = list(pattern_for(Event.PUNCT_ON)) + list(pattern_for(Event.DONE))
    check("cua en ordre", calls == expected)
    check("wait_idle", idle)

    muted: list[tuple[int, int]] = []
    quiet = Feedback(enabled=False, player=lambda f, d: muted.append((f, d)))
    quiet.play(Event.ERROR)
    quiet.close()
    check("desactivat no sona", muted == [])
    check("cada idioma te patro propi",
          len({pattern_for(Event.LANG_CA), pattern_for(Event.LANG_ES),
               pattern_for(Event.LANG_EN)}) == 3)

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def test_state() -> bool:
    from app.state import State, modes_label, status_line

    print("Estat:")
    failures = 0

    def check(label: str, got: str, expected: str) -> None:
        nonlocal failures
        ok = got == expected
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}  ({got!r})")

    check("inicial", status_line(State.IDLE, "ca", False, False),
          "[estat] IDLE · ca · modes: cap")
    check("escoltant amb puntuacio",
          status_line(State.LISTENING, "ca", True, False),
          "[estat] ESCOLTANT · ca · modes: PUNCT")
    check("transcrivint amb tot",
          status_line(State.TRANSCRIBING, "es", True, True),
          "[estat] TRANSCRIBUINT · es · modes: PUNCT+LLETRES")
    check("error amb lletres",
          status_line(State.ERROR, "en", False, True),
          "[estat] ERROR · en · modes: LLETRES")
    check("sense modes", modes_label(False, False), "cap")

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def test_instance() -> bool:
    import os
    import subprocess

    from app.instance import SingleInstance

    print("Instancia unica:")
    failures = 0

    def check(label: str, ok: bool) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}")

    name = f"Local\\CustormWispeFlow-test-{os.getpid()}"
    script = (
        "from app.instance import SingleInstance;"
        f"s = SingleInstance({name!r});"
        "print('already' if s.already_running else 'new');"
        "s.close()"
    )

    first = SingleInstance(name)
    try:
        check("primera instancia", not first.already_running)
        second = subprocess.run(
            [sys.executable, "-c", script], cwd=str(ROOT),
            capture_output=True, text=True, timeout=30,
        )
        check("segona detecta la primera", second.stdout.strip() == "already")
        check("segona sense errors", second.returncode == 0)
    finally:
        first.close()

    third = subprocess.run(
        [sys.executable, "-c", script], cwd=str(ROOT),
        capture_output=True, text=True, timeout=30,
    )
    check("despres de tancar torna a ser nova", third.stdout.strip() == "new")

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def test_undo() -> bool:
    from app.undo import LastInsert, Undoer

    print("Desfer:")
    failures = 0
    calls: list[tuple[object, ...]] = []

    def check(label: str, ok: bool) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}")

    def last(hwnd: int = 123, method: str = "paste",
             chars: int = 3) -> LastInsert:
        return LastInsert(text="x" * chars, method=method, hwnd=hwnd,
                          chars=chars)

    undoer = Undoer(
        foreground=lambda: 123,
        ctrl_z=lambda: calls.append(("ctrl_z",)),
        backspaces=lambda n: calls.append(("backspace", n)),
        modifiers_down=lambda vk: False,
    )

    ok, _ = undoer.undo(None)
    check("sense insercio", not ok and calls == [])

    ok, _ = undoer.undo(last(hwnd=999))
    check("finestra diferent", not ok and calls == [])

    ok, _ = undoer.undo(last(method="dry-run"))
    check("dry-run no es desfa", not ok and calls == [])

    ok, _ = undoer.undo(last(method="paste"))
    check("paste fa Ctrl+Z", ok and calls == [("ctrl_z",)])

    calls.clear()
    ok, _ = undoer.undo(last(method="type", chars=7))
    check("type fa retrocessos", ok and calls == [("backspace", 7)])

    calls.clear()
    ok, _ = undoer.undo(last(method="type", chars=800))
    check("limit de retrocessos", ok and calls == [("backspace", 500)])

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def test_hygiene() -> bool:
    import tempfile
    from pathlib import Path

    from app.history import trim_history
    from app.logs import reset_logging, setup_logging

    print("Higiene:")
    failures = 0

    def check(label: str, ok: bool) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        history = base / "history.jsonl"
        history.write_text(
            "".join(f'{{"n": {i}}}\n' for i in range(10)), encoding="utf-8",
        )
        removed = trim_history(history, 4)
        lines = history.read_text(encoding="utf-8").splitlines()
        check("retalla historial", removed == 6)
        check("conserva les ultimes",
              lines == [f'{{"n": {i}}}' for i in range(6, 10)])
        check("0 vol dir sense limit", trim_history(history, 0) == 0)

        log_dir = base / "logs"
        logger = setup_logging(log_dir)
        logger.info("prova de log 123")
        for handler in logger.handlers:
            handler.flush()
        check("escriu el log",
              "prova de log 123" in (log_dir / "dictate.log").read_text(
                  encoding="utf-8"))
        reset_logging()

    import dictate
    from app.config import load

    cfg = load()
    cfg.beeps = False
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        quiet = dictate.DictationApp(cfg, save_history=False)
        quiet.history = base / "quiet.jsonl"
        quiet._save_history("ca", "hola", 1.0, 0.5, "type")
        check("--no-history no escriu", not quiet.history.exists())

        loud = dictate.DictationApp(cfg, save_history=True)
        loud.history = base / "loud.jsonl"
        loud._save_history("ca", "hola", 1.0, 0.5, "type")
        check("historial normal si escriu", loud.history.exists())

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def test_focus_guard() -> bool:
    from app import insert as ins

    print("Guard de focus:")
    failures = 0

    def check(label: str, ok: bool) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"  {label}: {'OK' if ok else 'FALLA'}")

    original = {
        "foreground_window": ins.foreground_window,
        "_send": ins._send,
        "_clipboard_set": ins._clipboard_set,
        "send_ctrl_v": ins.send_ctrl_v,
        "type_text": ins.type_text,
        "paste_text": ins.paste_text,
    }
    try:
        ins.foreground_window = lambda: 999
        try:
            ins.type_text("hola", expected_hwnd=123)
            check("type avorta", False)
        except ins.InsertAborted as exc:
            check("type avorta", exc.chars_written == 0)

        sent: list[int] = []
        ins._send = lambda inputs: sent.append(len(inputs))
        ins.foreground_window = lambda: 123
        check("type amb focus correcte",
              ins.type_text("abc", expected_hwnd=123) == 3)
        check("type envia els caracters", sum(sent) == 6)

        calls: list[str] = []
        ins._clipboard_set = lambda text: True
        ins.send_ctrl_v = lambda: calls.append("ctrl_v")
        ins.foreground_window = lambda: 999
        try:
            ins.paste_text("hola", restore_clipboard=False, expected_hwnd=123)
            check("paste avorta", False)
        except ins.InsertAborted as exc:
            check("paste avorta", exc.chars_written == 0)
        check("paste no envia Ctrl+V", calls == [])

        ins.foreground_window = lambda: 123
        check("paste amb focus correcte",
              ins.paste_text("hola", restore_clipboard=False,
                             expected_hwnd=123) == 4)
        check("paste envia Ctrl+V", calls == ["ctrl_v"])

        def boom(text, expected_hwnd=None):  # noqa: ANN001
            raise ins.InsertAborted(2)

        ins.type_text = boom
        try:
            ins.insert("abc", mode="type", expected_hwnd=123)
            check("insert propaga l'avortament", False)
        except ins.InsertAborted as exc:
            check("insert propaga l'avortament", exc.chars_written == 2)
    finally:
        for name, value in original.items():
            setattr(ins, name, value)

    import contextlib
    import io

    import dictate
    from app.config import load as load_config
    from app.state import State

    cfg = load_config()
    cfg.beeps = False
    app = dictate.DictationApp(cfg, save_history=False)
    original_insert = dictate.insert

    def abort(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ins.InsertAborted(5)

    dictate.insert = abort
    app.log.disabled = True
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            app._deliver("ca", "hola mon", 1.0, 0.1, 1.0)
    finally:
        app.log.disabled = False
        dictate.insert = original_insert

    check("avortament registra el text parcial",
          app.last_insert is not None and app.last_insert.chars == 5
          and app.last_insert.method == "type")
    check("avortament deixa estat d'error", app.state == State.ERROR)

    print(f"  resultat: {'OK' if failures == 0 else 'FALLA'}\n")
    return failures == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-engine", action="store_true")
    parser.add_argument("--skip-insert", action="store_true")
    parser.add_argument("--skip-modes", action="store_true")
    parser.add_argument("--skip-feedback", action="store_true")
    parser.add_argument("--skip-state", action="store_true")
    parser.add_argument("--skip-undo", action="store_true")
    parser.add_argument("--skip-instance", action="store_true")
    parser.add_argument("--skip-hygiene", action="store_true")
    parser.add_argument("--skip-focus", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    ok = True
    if not args.skip_engine:
        ok = test_engine(args.config) and ok
    if not args.skip_modes:
        ok = test_text_modes(args.config) and ok
    if not args.skip_feedback:
        ok = test_feedback() and ok
    if not args.skip_state:
        ok = test_state() and ok
    if not args.skip_undo:
        ok = test_undo() and ok
    if not args.skip_instance:
        ok = test_instance() and ok
    if not args.skip_hygiene:
        ok = test_hygiene() and ok
    if not args.skip_focus:
        ok = test_focus_guard() and ok
    if not args.skip_insert:
        ok = test_insert() and ok

    print("TOT OK" if ok else "HI HA FALLADES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
