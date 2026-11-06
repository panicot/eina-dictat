# CustormWispeFlow

Dictat local per veu en català, castellà i anglès. Prem una tecla, parla i el text
apareix al camp que tingui el focus: un document, el navegador, la barra d'URLs o
qualsevol `input`.

Tot passa a l'ordinador: cap àudio surt del dispositiu.

## Estat

MVP funcional amb interfície d'escriptori. Ja fa:
- finestra de configuració amb dues pestanyes: **General** i **Models**
- safata del sistema i indicador flotant que no roba el focus
- tema fosc i clar
- catàleg de models amb descàrrega, progrés i assignació per idioma
- hotkey global (F8 per defecte), mode *toggle* o *hold*
- captura de micròfon, retall de silenci i transcripció amb Whisper
- model diferent per idioma (català afinat, castellà/anglès genèrics)
- inserció al cursor per dues vies: `SendInput` Unicode i porta-retalls + Ctrl+V
- canvi d'idioma en calent (`Ctrl+Shift+1/2/3`)
- historial a `history.jsonl`
- sigles i signes de puntuació dictats per veu
- desfer l'última inserció, instància única i guard de focus
- descàrrega de models en procés aïllat, amb cancel·lació i reprendre
- finestra de configuració amb mida adaptable i centratge a la pantalla

Encara no fa: transcripció en streaming i empaquetat en `.exe`.

## Requisits

- Windows 10/11 amb micròfon, o Linux amb X11 o Wayland (GNOME)
- Python 3.11+ (a Windows s'ha provat amb 3.13; no 3.14: `ctranslate2` encara no hi dona suport fiable)

## Instal·lació

### Windows

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Linux

#### Opció automàtica (Recomanada)

Executa l'script d'instal·lació assistida, que s'encarrega d'instal·lar els paquets del sistema (Debian/Ubuntu/Fedora), crear l'entorn virtual, instal·lar les dependències de Python, afegir l'usuari al grup `input` (per a Wayland) i crear la drecera d'escriptori:

```bash
chmod +x install_linux.sh
./install_linux.sh
```

> **Important (Wayland):** Si fas servir Wayland, cal que tanquis la sessió i tornis a entrar perquè el grup `input` s'apliqui correctament.

#### Opció manual

Si prefereixes fer la instal·lació pas a pas:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

##### Paquets del sistema per a X11:

```bash
# Debian/Ubuntu
sudo apt install xdotool xclip libportaudio2 python3-venv python3-dev build-essential

# Fedora
sudo dnf install xdotool xclip portaudio python3-devel gcc
```

##### Paquets del sistema per a Wayland (GNOME):

Wayland no permet llegir tecles globals ni injectar text directament com X11. Calen eines del sistema i permisos per llegir `/dev/input`:

```bash
# Debian/Ubuntu
sudo apt install ydotool wl-clipboard wtype libportaudio2 python3-venv python3-dev build-essential

# Fedora
sudo dnf install ydotool wl-clipboard wtype portaudio python3-devel gcc

# Permisos per als hotkeys globals (evdev)
sudo usermod -aG input $USER
# Tanca la sessió i torna a entrar perquè el canvi de grup s'apliqui.
```

> El grup `input` dona accés de lectura a tots els dispositius d'entrada. Si no
> el vols fer servir, crea una regla udev que doni accés només a `/dev/input/event*`.

El dimoni de `ydotool` ha d'estar en marxa. Segons la distribució pot ser una
unitat d'usuari o un servei del sistema:

```bash
systemctl --user enable --now ydotool   # o ydotoold, segons el paquet
# Si no hi ha cap unitat de systemd:
ydotoold &
```

Si `ydotoold` escolta en un socket no estàndard, exporta `YDOTOOL_SOCKET`.

La primera execució descarrega el model a `models/` (~500 MB).

## Comprovació de l'entorn

Abans d'obrir la interfície, comprova que hi hagi tot el que cal:

```bash
source .venv/bin/activate
python check_linux.py
```

El script revisa la sessió detectada, les eines del sistema (`xdotool`,
`ydotool`, `wtype`, `wl-clipboard`), els permisos de `/dev/input`, el dimoni
`ydotoold`, el porta-retalls, l'àudio i el model. Surt amb codi 0 si no hi ha
cap error. Per forçar un backend:

```bash
python check_linux.py --backend wayland
python check_linux.py --backend x11
```

També pot provar les dues peces que més fallen, sense obrir la GUI:

```bash
# Espera 15 segons que premis la tecla de dictat configurada.
python check_linux.py --hotkey-test

# Compte enrere de 5 segons i escriu el text al camp que tingui el focus.
# Fes clic abans en un editor de text buit.
python check_linux.py --type-test
```

### Validació manual a GNOME Wayland

1. `python check_linux.py --backend wayland` ha de sortir sense errors.
2. `--hotkey-test` ha de detectar la tecla (F8 per defecte).
3. `--type-test` ha d'escriure el text a l'editor on hagis fet clic.
4. Obre `python gui.py`, comprova la icona de la safata i dicta una frase en un
   editor, al navegador i a la barra d'URLs.
5. Prova accents i emojis amb `insert_mode = "paste"` (Wayland no garanteix
   `type` amb caràcters fora de la distribució de teclat).
6. Prem la tecla de desfer (F9 per defecte) just després d'una inserció.
7. Obre una segona còpia: ha d'avisar que ja n'hi ha una en marxa.

Si l'aplicació no apareix a la safata, GNOME necessita l'extensió
**AppIndicator and KStatusNotifierItem Support**; sense ella la finestra es
tanca en lloc d'amagar-se.

## Ús

### Llançar l'aplicació

**Linux (X11 o Wayland):**

L'aplicació està disponible al menú d'aplicacions (cerca `CustormWispeFlow`). O bé executa:

```bash
./start_dictate.sh
```

Si vols forçar el backend: `CWF_BACKEND=x11 ./start_dictate.sh` o `CWF_BACKEND=wayland ./start_dictate.sh`.

**Windows:**

Doble clic a `start_dictate.bat`, o bé:

```powershell
.\.venv\Scripts\activate
python gui.py
```

S'obre la finestra de configuració. La creu de la finestra l'amaga a la safata:
l'aplicació continua escoltant la tecla de dictat. Fes doble clic a la icona de
la safata per tornar-la a obrir.

La pestanya **General** permet triar:

- la **tecla per dictar** (captura la combinació que premis)
- el **micròfon** detectat, amb botó de refresc i prova de nivell
- el **model de transcripció** per a cada idioma

La pestanya **Models** mostra el catàleg, quins models ja tens al disc i quins
es poden descarregar, amb barra de progrés, cancel·lació i assignació a català,
castellà o anglès.

El catàleg inclou el model **Aina large-v3 3CatParla** (català, ~3,1 GB): molt
més precís, però pensat per GPU. En un N100 pot trigar desenes de segons per
frase i no afegeix puntuació.

Mentre dictes, un indicador flotant a la part inferior de la pantalla mostra
l'estat, el temps i l'idioma sense robar el focus. També hi ha els senyals
sonors de sempre.

Ves a qualsevol camp de text i:

| Tecla | Acció |
|---|---|
| `F8` | començar a escoltar / aturar i inserir |
| `F9` | desfer l'última inserció |
| `Ctrl+Shift+1` | català |
| `Ctrl+Shift+2` | castellà |
| `Ctrl+Shift+3` | anglès |
| `Ctrl+Shift+Q` | sortir |

La versió de consola continua disponible:

```powershell
python dictate.py
python dictate.py --file samples\ca_01.wav --dry-run
```

Només pot haver-hi **una instància** en marxa. Si engegues una segona, s'obre la
finestra de la primera en lloc de barallar-se pel hotkey. Per a proves:
`python dictate.py --allow-multiple`.

Amb la interfície gràfica no cal tenir cap terminal obert. Si fas servir
`dictate.py` en mode consola, el terminal ha de quedar obert mentre dictes. Els
senyals sonors indiquen l'estat sense haver de mirar la pantalla:

| So | Significat |
|---|---|
| to agut | escoltant |
| to mitjà | transcrivint |
| to molt agut | text inserit |
| dos tons greus descendents | error |
| dues notes ascendents | signes de puntuació activats |
| dues notes descendents | signes de puntuació desactivats |
| greu, greu, agut | deletreig activat |
| agut, greu, greu | deletreig desactivat |
| tres notes descendents | mode normal |
| 1, 2 o 3 polsos curts | idioma català, castellà o anglès |

Els tons se senten un darrere l'altre, mai solapats. Es poden desactivar amb
`beeps = false`.

A més, el terminal mostra una línia `[estat]` a cada canvi, amb l'idioma i els
modes actius:

```
[estat] ESCOLTANT · ca · modes: cap
[estat] TRANSCRIBUINT · ca · modes: cap
  · signes de puntuacio ON
  > exemple.
[estat] IDLE · ca · modes: PUNCT
```

Els modes poden ser `cap`, `PUNCT`, `LLETRES` o `PUNCT+LLETRES`.

## Dictar lletres i signes

### Sigles automàtiques

Si dius els noms de tres lletres o més seguides, s'escriuen com una sigla, sense
guions ni espais:

| Dius | Surt |
|---|---|
| `u erre ele` | `URL` |
| `ce efa efa` | `CFF` |
| `essa eme esse` | `SMS` |

Per no trencar el dictat normal, les seqüències curtes de paraules que també són
lletres (`a i o`, `la e`) es deixen tal com raja. Per a una **seqüència** calen
**3 lletres** i almenys **2 noms distintius** (`erre`, `efa`, `essa`…).

També s'ajunten les lletres que el model ja retorna separades (`S C F F` →
`SCFF`). El model està esbiaixat amb el vocabulari d'ordres i de noms de lletra,
cosa que fa que reconegui molt millor aquestes paraules que amb un prompt genèric.

Si dictes **un sol nom distintiu**, també s'escriu la lletra:

| Dius | Surt |
|---|---|
| `efa` | `F` |
| `essa` | `S` |
| `erre` | `R` |

Els noms que també són paraules normals (`a`, `de`, `te`, `ca`, `ve`, `be`) no es
converteixen sols, per no trencar el dictat. Per a aquests, activa
`lletra a lletra`.

Si l'hi dius amb la frase **la lletra**, també s'escriu, encara que el model
afegeixi ompliments:

| Dius | Surt |
|---|---|
| `escriu la lletra essa` | `escriu la lletra S` |
| `escriu la lletra, a, essa` | `escriu la lletra S` |

### Deletreig explícit

Per a una sola lletra o per barrejar paraules i lletres, activa el mode:

- **`lletra a lletra`** (o `mode lletres`) → activa
- **`fi lletra a lletra`** (o `fi mode lletres`) → desactiva
- **`mode normal`** → desactiva tot

Dins del mode, qualsevol nom de lletra es converteix:

| Dius | Surt |
|---|---|
| `a` | `A` |
| `a be ce` | `ABC` |
| `double u why zed` | `WYZ` |

El mode es manté entre dictats fins que el desactives.

### Signes de puntuació

Digues **`signes de puntuació`** i, a partir d'aquell moment, els noms de signes
es converteixen en símbols:

| Dius | Surt |
|---|---|
| `punt` | `.` |
| `coma` | `,` |
| `punt i coma` | `;` |
| `dos punts` | `:` |
| `arrova` | `@` |
| `barra` | `/` |
| `example punt com barra documents` | `example.com/documents` |

També entén dominis sencers (`punt com`, `punt cat`, `punt org`…) i signes com
`guio`, `guio baix`, `coixinet`, `percentatge`, `euro`, `parentesi oberta`,
`cometes`, `interrogant`, `exclamacio`, `punt i a part`, `nova linia`…

Per desactivar-lo:

- **`fi signes de puntuació`**
- **`mode normal`**

El mode és persistent: no cal repetir l'ordre a cada dictada. Si el que vols és
escriure literalment la paraula *punt*, desactiva el mode abans.

També reconeix les ordres en castellà (`signos de puntuación`, `punto`, `coma`,
`arroba`, `punto com`…) i en anglès (`punctuation mode`, `dot`, `comma`, `slash`,
`at sign`…).

> Consell: el reconeixement de veu pot transcriure `punt com` com `punt coma` o
> `pun com`. Si et passa sovint, afegeix la variant a `[dictionary]` de
> `config.toml`, per exemple `"pun com" = "punt com"`.

## Desfer l'última inserció

Prem `F9` (o la tecla que posis a `undo_hotkey`) i s'esborra l'últim text
inserit:

- si es va escriure amb `SendInput`, s'envien retrocessos exactament pels
  caràcters inserits;
- si es va enganxar amb el porta-retalls, s'envia `Ctrl+Z`.

Per seguretat, **només actua si la finestra en primer pla és la mateixa** on es
va inserir el text. Si has canviat de finestra, no toca res i avisa amb un so
d'error: així no s'esborra mai res d'una altra aplicació.

Només es pot desfer l'última inserció, i es perd en reiniciar l'app.

## Configuració

Tot és a `config.toml`:

| Opció | Per defecte | Descripció |
|---|---|---|
| `hotkey` | `f8` | tecla global; admet `ctrl+shift+...`, `f1`–`f24`, lletres |
| `undo_hotkey` | `f9` | desfer l'última inserció (només a la mateixa finestra) |
| `history_max_lines` | `2000` | retalla `history.jsonl` en arrencar; `0` = sense límit |
| `mode` | `toggle` | `toggle` (prémer) o `hold` (mantenir) |
| `language` | `ca` | idioma inicial |
| `threads` | `4` | fils de CPU |
| `insert_mode` | `auto` | `type`, `paste` o `auto` (llarg → porta-retalls) |
| `beeps` | `true` | senyals sonors d'inici/final |
| `theme` | `dark` | `dark` o `light` |
| `device` | buit | nom o índex del micròfon; es pot triar des de la UI |
| `dictionary` | buit | substitucions de noms/sigles després de transcriure |
| `initial_prompts` | cat/cast/anglès | context que esbiaixa el model (inclou el vocabulari d'ordres) |
| `spelling_auto` | `true` | detecta sigles de 3+ lletres (`u erre ele` → `URL`) |
| `spelling_uppercase` | `true` | les lletres deletrejades surten en majúscules |
| `spelling_separator` | `""` | separador entre lletres; `""` = cap |

La finestra de configuració desa els canvis a `config.toml` preservant els
comentaris. Els canvis de tecla, micròfon i model s'apliquen en calent sempre
que l'app no estigui transcrivint.

Per canviar de micròfon des de la consola:

```powershell
python dictate.py --list-devices
```

i posa el nom (o l'índex) a `device`.

## Logs i historial

- `history.jsonl` guarda cada dictada, amb el text inclòs. En arrencar es
  retallen les més antigues fins a `history_max_lines` (2000 per defecte;
  `0` = sense límit). Amb `--no-history` no s'hi escriu res.
- `logs/dictate.log` és rotatiu (2 MB × 3 fitxers) i **no conté el text**: només
  transicions d'estat, modes, llengua, latència, mètode d'inserció i errors.
  Amb `--verbose` també es mostra per consola.

## Proves

```powershell
# Motor + inserció (obre una finestra de test i escriu-hi)
python selftest.py

# Només inserció, sense carregar el model
python selftest.py --skip-engine

# Sense les proves que obren finestres o processos
python selftest.py --skip-engine --skip-insert --skip-instance

# Circuit complet amb un WAV, sense micròfon ni inserció real
python dictate.py --demo samples\ca_01.wav --dry-run
```

`--demo` és útil per comprovar que el hotkey i el motor funcionen sense parlar.
`--dry-run` evita escriure en finestres alienes. El test d'inserció tampoc no
envia cap tecla si una altra aplicació té el focus: en aquest cas es salta.

També pots transcriure un fitxer i sortir:

```powershell
python dictate.py --file samples\ca_01.wav
python dictate.py --file samples\ca_01.wav --insert   # insereix al camp actiu
python dictate.py --file samples\ca_03.wav --punct    # comença amb signes actius
python dictate.py --file samples\ca_03.wav --spell    # comença amb deletreig
```

## Com funciona

```
F8 (hotkey global: GetAsyncKeyState a Windows, pynput a X11, evdev a Wayland)
  → micròfon 16 kHz + retall de silenci
  → faster-whisper (model per idioma, int8)
  → diccionari personal
  → ordres de veu (puntuació / deletreig)
  → SendInput/xdotool/ydotool  o  porta-retalls + Ctrl+V
```

`SendInput` escriu caràcter a caràcter i respecta el cursor. Per a textos llargs
(o si `insert_mode = "paste"`) es fa servir el porta-retalls, que és l'únic camí
fiable cap a finestres elevades (executades com a Administrador).

Abans de començar, l'app apunta quina finestra té el focus i la torna a comprovar
durant la inserció. Si una altra aplicació el roba a mig escriure (una notificació,
un instal·lador), s'atura i avisa en lloc d'abocar el text a la finestra equivocada.
El que ja s'havia escrit es pot desfer amb `F9` o `Ctrl+Z`.

## Limitacions conegudes

- **Finestres elevades**: `SendInput` des d'un procés normal no hi arriba. Posa
  `insert_mode = "paste"` si has de dictar en una consola d'Administrador.
- **Linux X11**: cal `xdotool` per inserir text i `xclip`/`xsel` per al
  porta-retalls. Els caràcters Unicode depenen de la configuració del teclat.
- **Linux Wayland**: cal `ydotool` (o `wtype`) i `wl-clipboard`. Els hotkeys
  necessiten `evdev` i permisos de lectura a `/dev/input` (grup `input` o una
  regla udev). El guard de focus no està disponible: no es pot saber quina
  finestra té el focus.
- **Wayland i Unicode**: `ydotool type` depèn de la distribució de teclat. Per a
  accents, emojis o caràcters especials fes servir `insert_mode = "paste"`, que
  passa pel porta-retalls.
- **Apps que ignoren Ctrl+V** o tenen handlers propis poden fallar amb el mode
  `paste`; prova `type`.
- **Latència**: ~2 s per frase de 7 s en aquest N100. És usable, no instantani.
- **F8 no se suprimeix**: en apps que l'utilitzin (VS Code, navegadors amb DevTools)
  també executa la seva acció. Canvia `hotkey` a `pause` o `ctrl+shift+space`.
- **F9 tampoc se suprimeix**: a l'Outlook envia/rebre i a l'Excel recalcula. Si et
  molesta, canvia `undo_hotkey` a `ctrl+shift+backspace`.
- **Precisió**: el model afinat en català va molt bé en parla clara; amb soroll o
  noms propis caldrà el diccionari.
- El terminal no es pot tancar; encara no hi ha tray ni overlay.

## Benchmark

Els resultats que justifiquen les decisions (model, `beam`, pla d'energia) són a
[`results/RESUM.md`](results/RESUM.md). Resum: `base` afinat en català dona ~9,6 %
de WER amb RTF 0,23; `small` no compensa en aquesta CPU.

## Properes passes

1. Provar amb la teva veu i ajustar el diccionari.
2. Streaming per reduir la latència percebuda.
3. Empaquetar amb PyInstaller i autostart.
4. Dreceres i perfils per aplicació (dictat en un idioma concret segons la finestra).

