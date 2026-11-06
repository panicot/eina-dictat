#!/usr/bin/env bash
# Instal·lador de CustormWispeFlow per a Linux (Debian/Ubuntu/Fedora).
# Crea el venv, instal·la dependències i configura permisos.

set -euo pipefail

echo "=== CustormWispeFlow: Instal·lació a Linux ==="
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1. Detectar distribució
ID="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
fi

echo "Sitema detectat: $PRETTY_NAME"

# 2. Instal·lar paquets del sistema (requereix sudo)
MISSING_PKGS=()
check_pkg() {
    if [ "$ID" = "fedora" ]; then
        rpm -q "$1" >/dev/null 2>&1 || MISSING_PKGS+=("$1")
    else
        dpkg -l "$1" >/dev/null 2>&1 || MISSING_PKGS+=("$1")
    fi
}

# Eines comunes
check_pkg "libportaudio2" 2>/dev/null || check_pkg "portaudio"
check_pkg "python3-venv"
check_pkg "python3-dev" 2>/dev/null || check_pkg "python3-devel"
check_pkg "build-essential" 2>/dev/null || check_pkg "gcc"

# Eines segons sessió
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    check_pkg "ydotool"
    check_pkg "wl-clipboard"
    check_pkg "wtype"
else
    check_pkg "xdotool"
    check_pkg "xclip"
fi

if [ ${#MISSING_PKGS[@]} -ne 0 ]; then
    echo "Cal instal·lar paquets del sistema: ${MISSING_PKGS[*]}"
    if [ "$ID" = "fedora" ]; then
        sudo dnf install -y "${MISSING_PKGS[@]}"
    else
        sudo apt update && sudo apt install -y "${MISSING_PKGS[@]}"
    fi
fi

# 3. Crear entorn virtual
if [ ! -d ".venv" ]; then
    echo "Creant entorn virtual..."
    python3 -m venv .venv
fi

echo "Instal·lant dependències de Python..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 4. Permisos (Wayland/evdev)
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    if ! groups | grep -q "\binput\b"; then
        echo "Afegint l'usuari al grup 'input' per als hotkeys..."
        sudo usermod -aG input "$USER"
        echo "AVÍS: Cal que tanquis la sessió i tornis a entrar perquè el canvi s'apliqui."
    fi
    
    # Intentar habilitar el servei de ydotool si existeix
    if systemctl --user list-unit-files | grep -q "ydotool"; then
        echo "Habilitant el servei ydotool..."
        systemctl --user enable --now ydotool || true
    fi
fi

# 5. Crear accés d'escriptori
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
# Ajustar el path a l'Exec del fitxer .desktop
sed "s|%k|$DIR|g" custormwispeflow.desktop > "$DESKTOP_DIR/custormwispeflow.desktop"
chmod +x "$DESKTOP_DIR/custormwispeflow.desktop"

# 6. Final
chmod +x start_dictate.sh
echo
echo "=== INSTAL·LACIÓ COMPLETADA ==="
echo "Pots llançar l'aplicació amb: ./start_dictate.sh"
echo "O des del menú d'aplicacions: CustormWispeFlow"
if groups | grep -vq "\binput\b" && [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    echo
    echo "RECORDATORI: No oblidis tancar la sessió i tornar a entrar."
fi
