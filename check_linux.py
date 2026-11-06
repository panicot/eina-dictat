#!/usr/bin/env python3
"""Comprovació de l'entorn de CustormWispeFlow a Linux.

Revisa la sessió gràfica, les eines del sistema, els permisos d'`evdev`, el
porta-retalls i l'àudio abans d'arrencar la interfície. També pot provar els
hotkeys i la inserció de text sense obrir la GUI.

Us:
  python check_linux.py                     # només comprovacions
  python check_linux.py --backend wayland   # força la detecció de sessió
  python check_linux.py --hotkey-test       # espera que premis la tecla de dictat
  python check_linux.py --type-test         # escriu un text al camp actiu

Codi de sortida: 0 si no hi ha cap error, 1 si n'hi ha.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

from app.backends import linux as backend  # noqa: E402

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
RESET = "\033[0m" if USE_COLOR else ""
BOLD = "\033[1m" if USE_COLOR else ""
GREEN = "\033[32m" if USE_COLOR else ""
YELLOW = "\033[33m" if USE_COLOR else ""
RED = "\033[31m" if USE_COLOR else ""
DIM = "\033[2m" if USE_COLOR else ""


class Report:
    """Recull els resultats i els imprimeix a mesura que es fan."""

    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    def section(self, title: str) -> None:
        print(f"\n{BOLD}{title}{RESET}")

    def ok(self, label: str, detail: str = "") -> None:
        suffix = f"  {DIM}{detail}{RESET}" if detail else ""
        print(f"  {GREEN}OK{RESET}     {label}{suffix}")

    def warn(self, label: str, detail: str = "") -> None:
        self.warnings += 1
        suffix = f"  {DIM}{detail}{RESET}" if detail else ""
        print(f"  {YELLOW}AVIS{RESET}   {label}{suffix}")

    def fail(self, label: str, detail: str = "") -> None:
        self.failures += 1
        suffix = f"  {DIM}{detail}{RESET}" if detail else ""
        print(f"  {RED}ERROR{RESET}  {label}{suffix}")

    def info(self, label: str, detail: str = "") -> None:
        suffix = f"  {DIM}{detail}{RESET}" if detail else ""
        print(f"         {label}{suffix}")

    def hint(self, text: str) -> None:
        for line in text.splitlines():
            print(f"         {DIM}{line}{RESET}")


# ---------------------------------------------------------------- utilitats


def _run(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _import_ok(module: str) -> tuple[bool, str]:
    try:
        imported = __import__(module)
    except Exception as exc:  # noqa: BLE001 - qualsevol error vol dir que no hi és
        return False, str(exc)
    version = getattr(imported, "__version__", "")
    return True, str(version)


# ------------------------------------------------------------- comprovacions


def check_system(report: Report) -> None:
    report.section("Sistema")

    if sys.platform == "linux":
        report.ok("plataforma", "linux")
    else:
        report.warn(
            "plataforma",
            f"{sys.platform}: aquest script està pensat per a Linux",
        )

    version = sys.version_info
    label = f"{version.major}.{version.minor}.{version.micro}"
    if version >= (3, 11):
        report.ok("Python", label)
    else:
        report.fail("Python", f"{label}: cal 3.11 o superior")

    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        report.ok("entorn virtual", sys.prefix)
    else:
        report.warn(
            "entorn virtual",
            "no s'ha detectat cap venv actiu (source .venv/bin/activate)",
        )


def check_session(report: Report) -> bool:
    report.section("Sessió gràfica")

    for name in (
        "XDG_SESSION_TYPE",
        "XDG_CURRENT_DESKTOP",
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "CWF_BACKEND",
    ):
        value = os.environ.get(name)
        if value:
            report.info(name, value)

    wayland = backend._session_is_wayland()
    if wayland:
        report.ok("backend", "Wayland")
        if not os.environ.get("WAYLAND_DISPLAY"):
            report.warn(
                "WAYLAND_DISPLAY",
                "no definit; s'ha forçat Wayland amb CWF_BACKEND",
            )
    else:
        report.ok("backend", "X11")
        if not os.environ.get("DISPLAY"):
            report.fail(
                "DISPLAY",
                "no definit; no sembla una sessió gràfica",
            )
    return wayland


def check_x11(report: Report) -> None:
    report.section("X11")

    xdotool = shutil.which("xdotool")
    if not xdotool:
        report.fail(
            "xdotool",
            "no trobat; cal per inserir text i consultar la finestra activa",
        )
        report.hint("sudo apt install xdotool   # o: sudo dnf install xdotool")
    else:
        result = _run([xdotool, "getactivewindow"])
        if result is not None and result.returncode == 0:
            report.ok("xdotool", f"{xdotool} (finestra {result.stdout.strip()})")
        else:
            report.warn(
                "xdotool",
                "instal·lat però no pot consultar la finestra activa",
            )

    clipboard = shutil.which("xclip") or shutil.which("xsel")
    if clipboard:
        report.ok("porta-retalls", clipboard)
    else:
        report.fail(
            "porta-retalls",
            "cal xclip o xsel per al mode paste",
        )
        report.hint("sudo apt install xclip   # o: sudo dnf install xclip")

    found, detail = _import_ok("pynput")
    if found:
        report.ok("pynput", detail)
    else:
        report.fail("pynput", "no instal·lat")
        report.hint("pip install pynput")


def check_wayland(report: Report) -> None:
    report.section("Wayland")

    found, detail = _import_ok("evdev")
    if found:
        report.ok("evdev", detail)
    else:
        report.fail("evdev", "no instal·lat; sense això no hi ha hotkeys")
        report.hint(
            "pip install evdev\n"
            "Si falla la compilació: sudo apt install linux-headers-$(uname -r) python3-dev"
        )

    # Grup `input`: el listener necessita llegir /dev/input/event*.
    groups: set[str] = set()
    try:
        import grp

        groups = {grp.getgrgid(gid).gr_name for gid in os.getgroups()}
    except Exception:  # noqa: BLE001 - en un entorn estrany, ignorem-ho
        pass

    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() == 0:
        report.ok("grup input", "s'executa com a root")
    elif "input" in groups:
        report.ok("grup input", "l'usuari hi pertany")
    else:
        report.fail(
            "grup input",
            "l'usuari no hi pertany; no podrà llegir /dev/input",
        )
        report.hint(
            "sudo usermod -aG input $USER\n"
            "Tanca la sessió i torna a entrar perquè el canvi s'apliqui."
        )

    if found:
        try:
            devices, denied = backend._open_evdev_keyboards()
        except Exception as exc:  # noqa: BLE001
            report.fail("teclats", str(exc))
            devices, denied = [], []

        try:
            if devices:
                names = [
                    getattr(device, "name", "?") for device in devices
                ]
                report.ok("teclats llegibles", ", ".join(sorted(names)))
                report.info("dispositius", str(len(devices)))
            elif denied:
                report.fail(
                    "teclats llegibles",
                    f"{len(denied)} dispositius sense permís de lectura",
                )
                report.hint(
                    "Comprova el grup `input` o una regla udev per a "
                    "/dev/input/event*."
                )
            else:
                report.fail(
                    "teclats llegibles",
                    "no s'ha trobat cap teclat amb /dev/input/event*",
                )
        finally:
            for device in devices:
                try:
                    device.close()
                except Exception:  # noqa: BLE001
                    pass

    ydotool = shutil.which("ydotool")
    wtype = shutil.which("wtype")
    if ydotool:
        report.ok("ydotool", ydotool)
        socket = _ydotoold_socket()
        if socket is not None:
            report.ok("ydotoold", f"socket {socket}")
        elif _ydotoold_running():
            report.ok("ydotoold", "procés en marxa (socket no localitzat)")
        else:
            report.fail(
                "ydotoold",
                "no s'ha detectat el dimoni; sense ell ydotool no injecta res",
            )
            report.hint(
                "systemctl --user enable --now ydotool   # o: ydotoold &\n"
                "Si el socket és en un altre lloc: export YDOTOOL_SOCKET=/ruta"
            )
    else:
        report.warn(
            "ydotool",
            "no trobat; es farà servir wtype si hi és",
        )
        report.hint("sudo apt install ydotool   # o: sudo dnf install ydotool")

    if wtype:
        report.ok("wtype", f"{wtype} (alternativa)")
    elif not ydotool:
        report.fail(
            "injector",
            "no hi ha ni ydotool ni wtype; no es podrà escriure text",
        )
        report.hint(
            "sudo apt install ydotool wtype   # o: sudo dnf install ydotool wtype"
        )

    wl_copy = shutil.which("wl-copy")
    wl_paste = shutil.which("wl-paste")
    if wl_copy and wl_paste:
        report.ok("wl-clipboard", f"{wl_copy}, {wl_paste}")
    else:
        report.fail(
            "wl-clipboard",
            "falta wl-copy o wl-paste; el mode paste no funcionarà",
        )
        report.hint(
            "sudo apt install wl-clipboard   # o: sudo dnf install wl-clipboard"
        )


def _ydotoold_socket() -> Path | None:
    candidates: list[Path] = []
    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        candidates.append(Path(configured))

    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        candidates.append(Path(runtime) / ".ydotool_socket")

    if hasattr(os, "getuid"):
        candidates.append(Path(f"/run/user/{os.getuid()}/.ydotool_socket"))

    candidates.append(Path("/tmp/.ydotool_socket"))
    try:
        candidates.append(Path.home() / ".ydotool_socket")
    except RuntimeError:
        pass

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def _ydotoold_running() -> bool:
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False

    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if comm.strip() in ("ydotoold", "ydotool"):
            return True
    return False


def check_common(report: Report) -> None:
    report.section("Aplicació")

    found, detail = _import_ok("PySide6")
    if found:
        report.ok("PySide6", detail)
    else:
        report.fail("PySide6", "no instal·lat")
        report.hint("pip install -r requirements.txt")

    try:
        from app import config as app_config

        cfg = app_config.load()
        report.ok(
            "config.toml",
            f"hotkey {cfg.hotkey}, desfer {cfg.undo_hotkey}, "
            f"inserció {cfg.insert_mode}",
        )
        if cfg.insert_mode == "type":
            report.warn(
                "insert_mode",
                "a Wayland `type` depèn de la distribució de teclat; "
                "per a accents i emojis fes servir paste",
            )
    except Exception as exc:  # noqa: BLE001
        report.fail("config.toml", str(exc))

    models = ROOT / "models"
    downloaded: list[Path] = []
    if models.is_dir():
        try:
            downloaded = [
                p for p in models.iterdir() if p.is_dir() and any(p.iterdir())
            ]
        except OSError:
            downloaded = []
    if downloaded:
        report.ok("models", f"{len(downloaded)} model(s) a models/")
    else:
        report.warn(
            "models",
            "cap model descarregat encara (es farà la primera vegada)",
        )

    if sys.platform == "linux":
        first = backend.SingleInstance("CWF-check")
        second = backend.SingleInstance("CWF-check")
        try:
            if first.handle is None:
                report.warn(
                    "instància única",
                    "no s'ha pogut crear el fitxer de bloqueig",
                )
            elif second.already_running:
                report.ok("instància única", str(first.path))
            else:
                report.fail(
                    "instància única",
                    "el bloqueig no funciona; es podrien obrir dues còpies",
                )
        finally:
            second.close()
            first.close()
            try:
                if first.handle is None:
                    Path(first.path).unlink(missing_ok=True)
            except (AttributeError, OSError):
                pass
    else:
        report.info("instància única", "només es comprova a Linux")


def check_audio(report: Report) -> None:
    report.section("Àudio")

    try:
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001
        report.fail("sounddevice", str(exc))
        report.hint(
            "sudo apt install libportaudio2   # o: sudo dnf install portaudio"
        )
        return

    try:
        devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        report.fail("PortAudio", str(exc))
        report.hint(
            "Comprova que el servei d'àudio (PipeWire/PulseAudio) funcioni."
        )
        return

    inputs = [d for d in devices if d["max_input_channels"] > 0]
    outputs = [d for d in devices if d["max_output_channels"] > 0]

    if inputs:
        try:
            default_input = sd.query_devices(kind="input")
            name = default_input["name"]
        except Exception:  # noqa: BLE001
            name = inputs[0]["name"]
        report.ok("micròfon", f"{len(inputs)} entrada(es), per defecte: {name}")
    else:
        report.fail("micròfon", "no s'ha detectat cap entrada d'àudio")

    if outputs:
        report.ok("sortida", f"{len(outputs)} sortida(es) per als senyals")
    else:
        report.warn("sortida", "cap sortida; els senyals sonors se saltaran")


# ------------------------------------------------------------ proves reals


def run_hotkey_test(report: Report, combo: str, seconds: float = 15.0) -> None:
    report.section("Prova de hotkey")
    pressed = threading.Event()
    manager = backend.HotkeyManager()
    manager.add(combo, pressed.set)

    print(f"  Prem {BOLD}{combo}{RESET} durant els pròxims "
          f"{int(seconds)} segons…")
    try:
        manager.start()
    except Exception as exc:  # noqa: BLE001
        report.fail("listener", str(exc))
        return
    try:
        if pressed.wait(seconds):
            report.ok("hotkey", f"detectada ({combo})")
        else:
            report.fail(
                "hotkey",
                f"no s'ha detectat {combo} en {int(seconds)} s",
            )
    finally:
        manager.stop()


def run_type_test(report: Report, text: str) -> None:
    report.section("Prova d'inserció")
    print("  Fes clic en un editor de text buit. Escriuré el text en 5 segons…")
    for remaining in range(5, 0, -1):
        print(f"  {remaining}…", end="\r", flush=True)
        time.sleep(1)
    print(" " * 20, end="\r")

    try:
        written = backend.type_text(text)
    except Exception as exc:  # noqa: BLE001
        report.fail("inserció", str(exc))
        return
    report.ok("inserció", f"{written} caràcters enviats")
    report.hint(f"Text esperat: {text}")


# --------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprova l'entorn de CustormWispeFlow a Linux.",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "x11", "wayland"),
        default="auto",
        help="força el backend igual que CWF_BACKEND",
    )
    parser.add_argument(
        "--hotkey-test",
        action="store_true",
        help="espera que premis la tecla de dictat configurada",
    )
    parser.add_argument(
        "--type-test",
        nargs="?",
        const="Hola, això és una prova de CustormWispeFlow.",
        default=None,
        metavar="TEXT",
        help="escriu TEXT (o un text per defecte) al camp actiu",
    )
    args = parser.parse_args()

    if args.backend != "auto":
        os.environ["CWF_BACKEND"] = args.backend

    report = Report()
    print(f"{BOLD}CustormWispeFlow · comprovació de l'entorn{RESET}")

    check_system(report)
    if sys.platform == "linux":
        wayland = check_session(report)
        if wayland:
            check_wayland(report)
        else:
            check_x11(report)
    elif args.backend != "auto":
        report.section("Sessió gràfica")
        report.warn(
            "plataforma",
            f"comprovacions de {args.backend} forçades fora de Linux",
        )
        if args.backend == "wayland":
            check_wayland(report)
        else:
            check_x11(report)
    else:
        report.section("Sessió gràfica")
        report.info("omès", "només s'executa a Linux (força-ho amb --backend)")
    check_common(report)
    check_audio(report)

    if args.hotkey_test or args.type_test is not None:
        try:
            from app import config as app_config

            combo = app_config.load().hotkey
        except Exception:  # noqa: BLE001
            combo = "f8"
    if args.hotkey_test:
        run_hotkey_test(report, combo)
    if args.type_test is not None:
        run_type_test(report, args.type_test)

    print()
    if report.failures:
        print(
            f"{RED}{report.failures} error(s){RESET}"
            + (f", {report.warnings} avís(os)" if report.warnings else "")
        )
        return 1
    if report.warnings:
        print(f"{YELLOW}{report.warnings} avís(os){RESET}, cap error")
    else:
        print(f"{GREEN}TOT OK{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
