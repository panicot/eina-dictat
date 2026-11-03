# Resum del benchmark — 31/10/2026

Màquina: Intel N100 (4 nuclis), ~8 GB RAM, sense GPU, Windows. Python 3.13,
`faster-whisper 1.2.1`, `compute_type=int8`, `beam_size=1`, VAD Silero activat,
pla d'energia **Equilibrat**.

Mostres: 5 WAV de 6–10 s generades amb `edge-tts` (veu sintètica, sense soroll).
WER calculat sobre el text de referència.

## Català (3 mostres)

| Model | Carrega | Latència | RTF | WER |
|---|---:|---:|---:|---:|
| `base` genèric | 2,2 s | 1,67 s | 0,21 | 26,4 % |
| `small` genèric | 3,7 s | 6,20 s | 0,82 | 11,0 % |
| `Jarbas/faster-whisper-base-ca-cv13` | 2,0 s* | **1,78 s** | **0,23** | **9,6 %** |
| `Jarbas/faster-whisper-base-ca-cv13` (beam 5) | 2,0 s | 1,69 s | 0,23 | 9,6 % |
| `Jarbas/faster-whisper-small-ca-cv13` | 3,0 s* | 4,86 s | 0,64 | 11,1 % |

\* La primera carrega inclou la descàrrega; les posteriors són 2–6 s.

- El **base afinat en català** dona la mateixa qualitat que `small` amb **~4× menys càlcul**.
- `beam 5` no millora res respecte de `beam 1` i afegeix complexitat.
- `small` i `small-ca` són **massa lents** per dictar en aquesta màquina (RTF ≥ 0,5).
- La mostra `ca_03` (URL dictada: "example punt com barra documents") és el pitjor cas
  per a tots els models. Caldrà normalització específica.

## Multilingüe (detecció automàtica, 1 passada)

| Model | Latència | RTF | WER ca | WER es | WER en |
|---|---:|---:|---:|---:|---:|
| `base` | 2,43 s | 0,34 | 21,7 % | 11,1 % | 0,0 % |
| `small` | 8,89 s | 1,28 | 8,7 % | 16,7 % | 0,0 % |

- `language="auto"` afegeix ~30–100 % de latència respecte de forçar l'idioma.
- El `base` genèric va bé en **castellà i anglès**; en català necessita el model afinat.
- Conclusió pràctica: **un model per idioma**, seleccionat per l'usuari, no `auto`.

## Efecte del pla d'energia

Amb **Rendiment alt**, `small` va passar de RTF 0,57 a 0,50 en la mateixa mostra
(~12 % més ràpid). L'N100 també mostra variació entre execucions per calor/càrrega:
cal mesurar amb la màquina freda i el pla fixat.

## Limitacions d'aquest benchmark

1. **Veu sintètica**: el WER real amb micròfon serà pitjor (soroll, pauses, muletilles).
2. **3 mostres en català**: cada paraula val ~4,3 % de WER; les diferències petites no són significatives.
3. **Fine-tunes de 2024** basats en *Common Voice* (parla llegida): poden generalitzar pitjor
   a dictat espontani que el `small` genèric.
4. No s'ha provat cap API al núvol (falta clau).

## Proper pas

1. Gravar 3–5 mostres reals per idioma:
   ```powershell
   python record.py --name real_ca_01 --seconds 8
   python record.py --name real_ca_02 --text "el text exacte"
   ```
2. Repetir el benchmark amb `--samples-dir samples` i comparar.
3. Decidir motor: local `base-ca` (~1,7 s) vs núvol (~0,5 s estimat) o híbrid.
