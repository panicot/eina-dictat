#!/usr/bin/env bash
# Llançador de CustormWispeFlow per a Linux.
# Detecta l'entorn, activa el venv i arrenca la GUI.

set -euo pipefail

# Directori de l'script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1. Comprovació del venv
if [ ! -d ".venv" ]; then
    echo "ERROR: No s'ha trobat l'entorn virtual (.venv)."
    echo "Executa './install_linux.sh' primer."
    exit 1
fi

# 2. Comprovació de la sessió
if [ -z "${XDG_SESSION_TYPE:-}" ]; then
    # Intenta detectar-la si no està definida
    if [ -n "${WAYLAND_DISPLAY:-}" ]; then
        export XDG_SESSION_TYPE="wayland"
    else
        export XDG_SESSION_TYPE="x11"
    fi
fi

# 3. Comprovació d'eines segons la sessió
MISSING=()
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    command -v ydotool >/dev/null 2>&1 || MISSING+=("ydotool")
    command -v wl-copy >/dev/null 2>&1 || MISSING+=("wl-clipboard")
else
    command -v xdotool >/dev/null 2>&1 || MISSING+=("xdotool")
    command -v xclip >/dev/null 2>&1 || command -v xsel >/dev/null 2>&1 || MISSING+=("xclip/xsel")
fi

if [ ${#MISSING[@]} -ne 0 ]; then
    echo "AVÍS: Falten eines del sistema per a la sessió $XDG_SESSION_TYPE: ${MISSING[*]}"
    echo "L'aplicació pot fallar en inserir text o fer servir el porta-retalls."
    echo "Consulta el README.md per a les instruccions d'instal·lació."
    echo
fi

# 4. Execució
echo "Arrencant CustormWispeFlow ($XDG_SESSION_TYPE)..."
exec ".venv/bin/python" gui.py "$@"
