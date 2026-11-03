"""Modes de veu: deletreig de lletres i signes de puntuacio.

- Deletreig automatic: una sequencia de 3+ noms de lletra amb almenys 2 de
  distintius es converteix en sigla ("u erre ele" -> "URL"). Les sequences
  formades nomes per a/e/i/o/u es deixen igual, perque son paraules normals.
- Mode deletreig explicit: "lletra a lletra" activa la conversio de qualsevol
  nom de lletra, incloent una sola lletra i noms anglesos.
- Mode signes de puntuacio: "signes de puntuacio" activa la substitucio de noms
  de signes pels simbols ("punt" -> "."). "fi signes de puntuacio" el desactiva.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# --- noms de lletra ---------------------------------------------------------

CATALAN_LETTERS = {
    "a": "A", "be": "B", "ce": "C", "de": "D", "e": "E", "efa": "F", "ge": "G",
    "hac": "H", "i": "I", "jota": "J", "ca": "K", "ela": "L", "ema": "M",
    "ena": "N", "o": "O", "pe": "P", "cu": "Q", "erra": "R", "essa": "S",
    "te": "T", "u": "U", "ve": "V", "xeix": "X", "i grega": "Y", "zeta": "Z",
    "doble ve": "W", "ela geminada": "L·L",
    # variants castellanes d'ús habitual entre parlants catalans
    "erre": "R", "ele": "L", "efe": "F", "hache": "H", "eme": "M", "ene": "N",
    "ese": "S", "uve": "V", "equis": "X", "ye": "Y", "ka": "K",
    # confusions habituals del model amb la lletra U ("u erre ele" -> "ho erre ela")
    "ho": "U", "hu": "U",
}

SPANISH_LETTERS = {
    "efe": "F", "hache": "H", "ele": "L", "eme": "M", "ene": "N", "eñe": "Ñ",
    "ese": "S", "uve": "V", "uve doble": "W", "equis": "X", "ye": "Y", "ka": "K",
}

# Nomes s'accepten en mode deletreig explicit: en dictat normal son paraules.
ENGLISH_LETTERS = {
    "double u": "W", "double you": "W", "why": "Y", "ex": "X", "zee": "Z",
    "zed": "Z", "cue": "Q", "are": "R", "bee": "B", "see": "C", "dee": "D",
    "ee": "E", "ef": "F", "gee": "G", "aitch": "H", "eye": "I", "jay": "J",
    "kay": "K", "el": "L", "em": "M", "en": "N", "oh": "O", "pee": "P",
    "queue": "Q", "ar": "R", "ess": "S", "tee": "T", "you": "U", "vee": "V",
}

LETTERS = {**CATALAN_LETTERS, **SPANISH_LETTERS, **ENGLISH_LETTERS}

# Noms prou distintius per convertir-se quan son l'unic que s'ha dit.
# Els que tambe son paraules freqüents ("a", "de", "te", "ca", "ve", "be")
# queden fora: caldria el mode "lletra a lletra".
SAFE_SINGLE = {
    "efa", "hac", "jota", "ela", "ema", "ena", "erra", "essa", "xeix", "zeta",
    "cu", "ce", "ge", "pe", "i grega", "doble ve", "ela geminada",
    "efe", "hache", "ele", "eme", "ene", "eñe", "uve", "equis", "ye", "ka",
}

# Noms que tambe son paraules o preposicions freqüents: no serveixen per
# activar el deletreig automatic.
WEAK_NAMES = {
    "a", "e", "i", "o", "u", "de", "te", "pe", "be", "ce", "ge", "ve",
    "ho", "hu",
}

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
GAP_RE = re.compile(r"[\s,.\-·'\"()]*")

# --- signes de puntuacio ----------------------------------------------------

PUNCTUATION = {
    # formats i salts
    "punt i a part": ".\n\n",
    "punt i seguit": ". ",
    "nou paragraf": "\n\n",
    "nou paràgraf": "\n\n",
    "nova linia": "\n",
    "nova línia": "\n",
    "tabulador": "\t",
    "espai": " ",
    # signes
    "punts suspensius": "...",
    "punt i coma": ";",
    "punt volat": "·",
    "dos punts": ":",
    "punt": ".",
    "coma": ",",
    "signe d'interrogacio": "?",
    "signe d'interrogació": "?",
    "signe d'exclamacio": "!",
    "signe d'exclamació": "!",
    "interrogant": "?",
    "exclamacio": "!",
    "exclamació": "!",
    "guio baix": "_",
    "guió baix": "_",
    "guio": "-",
    "guió": "-",
    "barra invertida": "\\",
    "barra": "/",
    "arrova": "@",
    "arroba": "@",
    "coixinet": "#",
    "hashtag": "#",
    "almohadilla": "#",
    "parentesi oberta": "(",
    "parentesi obert": "(",
    "parèntesi obert": "(",
    "parentesi tancada": ")",
    "parentesi tancat": ")",
    "parèntesi tancat": ")",
    "claudator obert": "[",
    "claudàtor obert": "[",
    "claudator tancat": "]",
    "claudàtor tancat": "]",
    "clau oberta": "{",
    "clau obert": "{",
    "clau tancada": "}",
    "clau tancat": "}",
    "cometes": '"',
    "cometa": '"',
    "apostrof": "'",
    "apòstrof": "'",
    "percentatge": "%",
    "signe de percentatge": "%",
    "euro": "€",
    "dolar": "$",
    "dòlar": "$",
    "asterisc": "*",
    "signe mes": "+",
    "signe més": "+",
    "signe igual": "=",
    "menor que": "<",
    "major que": ">",
    "barra vertical": "|",
    "titlla": "~",
    "circumflex": "^",
    "accent greu": "`",
    # dominis habituals
    "punt com": ".com",
    "punt cat": ".cat",
    "punt org": ".org",
    "punt net": ".net",
    "punt eu": ".eu",
    "punt es": ".es",
    "punt edu": ".edu",
    "punt gov": ".gov",
    "punt info": ".info",
    "punt io": ".io",
    "punt dev": ".dev",
    "punt app": ".app",
    # castellà
    "punto y aparte": ".\n\n",
    "punto y seguido": ". ",
    "punto y coma": ";",
    "nuevo párrafo": "\n\n",
    "nuevo parrafo": "\n\n",
    "nueva línea": "\n",
    "nueva linea": "\n",
    "punto com": ".com",
    "punto cat": ".cat",
    "punto org": ".org",
    "punto net": ".net",
    "punto eu": ".eu",
    "punto es": ".es",
    "punto edu": ".edu",
    "punto gov": ".gov",
    "punto info": ".info",
    "punto io": ".io",
    "punto dev": ".dev",
    "punto app": ".app",
    "punto": ".",
    "signo de interrogación": "?",
    "signo de exclamación": "!",
    "interrogación": "?",
    "exclamación": "!",
    "guion bajo": "_",
    "guion": "-",
    "paréntesis abierto": "(",
    "paréntesis cerrado": ")",
    "corchete abierto": "[",
    "corchete cerrado": "]",
    "llave abierta": "{",
    "llave cerrada": "}",
    "comillas": '"',
    "apóstrofo": "'",
    "porcentaje": "%",
    "dólar": "$",
    "igual": "=",
    # anglès
    "full stop": ".",
    "period": ".",
    "comma": ",",
    "semicolon": ";",
    "colon": ":",
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "dot com": ".com",
    "dot cat": ".cat",
    "dot org": ".org",
    "dot net": ".net",
    "dot io": ".io",
    "dot dev": ".dev",
    "dot app": ".app",
    "dot": ".",
    "slash": "/",
    "backslash": "\\",
    "underscore": "_",
    "hyphen": "-",
    "dash": "-",
    "at sign": "@",
    "hash": "#",
    "percent": "%",
    "dollar": "$",
    "asterisk": "*",
    "open parenthesis": "(",
    "close parenthesis": ")",
    "open bracket": "[",
    "close bracket": "]",
    "open brace": "{",
    "close brace": "}",
    "quotation mark": '"',
    "apostrophe": "'",
    "new line": "\n",
    "new paragraph": "\n\n",
}

ON_PUNCTUATION = [
    "signes de puntuacio", "signes de puntuació",
    "signe de puntuacio", "signe de puntuació",
    "signos de puntuacion", "signos de puntuación",
    "modo puntuacio", "modo puntuació", "mode signes",
    "modo puntuacion", "modo puntuación",
    "punctuation mode",
]
OFF_PUNCTUATION = [
    "fi signes de puntuacio", "fi signes de puntuació",
    "fi mode puntuacio", "fi mode puntuació",
    "atura signes", "desactiva puntuacio", "desactiva puntuació",
    "fin signos de puntuacion", "fin signos de puntuación",
    "fin modo puntuacion", "fin modo puntuación",
    "end punctuation mode", "disable punctuation",
]
ON_SPELLING = [
    "lletra a lletra", "mode lletres", "mode deletreig",
    "deletreja", "deletrejar",
    "letra a letra", "modo letras", "modo deletreo",
    "spell mode", "spelling mode",
]
OFF_SPELLING = [
    "fi lletra a lletra", "fi mode lletres", "fi deletreig", "atura deletreig",
    "fin letra a letra", "fin modo letras", "fin deletreo",
    "end spell mode", "end spelling mode",
]
OFF_ALL = ["mode normal", "torna al mode normal", "modo normal",
           "normal mode", "turn off modes"]


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)


def _remove_phrase(text: str, phrase: str) -> tuple[str, bool]:
    # Consumim tambe la puntuacio que Whisper afegeix al final de l'ordre
    # ("signes de puntuacio."), si no quedaria un punt solt al text.
    pattern = re.compile(
        rf"(?<!\w){re.escape(phrase)}(?!\w)[ \t]*[,.;:!?…]*",
        re.IGNORECASE,
    )
    if not pattern.search(text):
        return text, False
    text = pattern.sub(" ", text)
    return _tidy_removal(text), True


def _tidy_removal(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([,.;:!?…])", r"\1", text)
    text = text.strip()
    if not re.search(r"\w", text):
        return ""
    return text


def _fold(token: str) -> str:
    """Minuscules sense accents ni puntuacio: 'Puntuació.' -> 'puntuacio'."""
    token = unicodedata.normalize("NFD", token.lower())
    token = "".join(ch for ch in token if unicodedata.category(ch) != "Mn")
    return token.strip(".,;:!?¡¿…()[]{}\"'«»-")


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= 0.7


# Variants que Whisper pot produir en lloc de "signes de puntuacio".
_PUNCT_MARKERS = {"signes", "signe", "sinyes", "sinye"}
_PUNCT_NOISE = {"cinc", "5", "sink", "sinc"}
_PUNCT_FILLER = {"de", "d", "nascs", "nasc", "nes", "ns", "els", "les"}
# Frases que demanen expressament una sola lletra ("escriu la lletra essa").
# S'accepten ompliments frequents del model ("la lletre", "el lletra").
LETTER_PHRASES = (
    "la lletra", "el lletra", "la lletre", "el lletre", "la letra", "el letra",
)

_PUNCT_OFF = {"fi", "final", "atura", "desactiva", "apaga", "tanca", "stop", "para"}


class TextModes:
    def __init__(self, config) -> None:  # noqa: ANN001
        self.spelling_auto = bool(getattr(config, "spelling_auto", True))
        self.spelling_uppercase = bool(getattr(config, "spelling_uppercase", True))
        self.separator = str(getattr(config, "spelling_separator", ""))
        self.spelling_mode = False
        self.punctuation_mode = False
        self.events: list[str] = []

    # ---- API ----

    def transform(self, text: str) -> str:
        self.events = []
        text = self._commands(text)
        # Primer la puntuacio: si no, en mode deletreig la "i" de "punt i coma"
        # es convertia en la lletra I abans d'arribar al signe.
        if self.punctuation_mode:
            text = self._punctuate(text)
        text = self._letter_phrase(text)
        text = self._spell(text)
        return text.strip()

    # ---- ordres de veu ----

    def _commands(self, text: str) -> str:
        changed = True
        while changed:
            changed = False
            for phrase in OFF_ALL:
                text, hit = _remove_phrase(text, phrase)
                if hit:
                    changed = True
                    if self.punctuation_mode or self.spelling_mode:
                        self.punctuation_mode = False
                        self.spelling_mode = False
                        self.events.append("mode normal")
            for phrase in OFF_PUNCTUATION:
                text, hit = _remove_phrase(text, phrase)
                if hit:
                    changed = True
                    if self.punctuation_mode:
                        self.punctuation_mode = False
                        self.events.append("signes de puntuacio OFF")
            for phrase in OFF_SPELLING:
                text, hit = _remove_phrase(text, phrase)
                if hit:
                    changed = True
                    if self.spelling_mode:
                        self.spelling_mode = False
                        self.events.append("deletreig OFF")
            for phrase in ON_PUNCTUATION:
                text, hit = _remove_phrase(text, phrase)
                if hit:
                    changed = True
                    if not self.punctuation_mode:
                        self.punctuation_mode = True
                        self.events.append("signes de puntuacio ON")
            for phrase in ON_SPELLING:
                text, hit = _remove_phrase(text, phrase)
                if hit:
                    changed = True
                    if not self.spelling_mode:
                        self.spelling_mode = True
                        self.events.append("deletreig ON")

            fuzzy = self._fuzzy_punct_command(text)
            if fuzzy is not None:
                start, end, is_off = fuzzy
                text = _tidy_removal(f"{text[:start]} {text[end:]}")
                changed = True
                if is_off:
                    if self.punctuation_mode:
                        self.punctuation_mode = False
                        self.events.append("signes de puntuacio OFF")
                elif not self.punctuation_mode:
                    self.punctuation_mode = True
                    self.events.append("signes de puntuacio ON")
        return text

    def _fuzzy_punct_command(self, text: str) -> tuple[int, int, bool] | None:
        """Detecta variants que Whisper inventa ('Sinnes de puntuacio',
        'Signes d'opuntuacio', 'Cinc nascs de puntuacio', '5 nes de
        puntuacio') i retorna el tros a eliminar i si l'ordre es d'activar o
        desactivar."""
        tokens = list(re.finditer(r"\S+", text))
        for index, token in enumerate(tokens):
            word = _fold(token.group())
            if "puntuaci" not in word:
                continue

            previous = [_fold(t.group()) for t in tokens[max(0, index - 5):index]]
            near = previous[-2:]
            recent = previous[-3:]

            # "de" pot venir separat o enganxat al mateix mot:
            # "d'opuntuacio", "depuntuacio".
            merged_de = word.startswith("d") or word.startswith("o")
            has_de = "de" in previous or "d" in previous or merged_de
            sign_like = any(
                item in _PUNCT_MARKERS or _similar(item, "signes")
                for item in near
            )
            if not has_de and not sign_like:
                continue

            noise_like = (
                any(item in _PUNCT_NOISE for item in recent)
                and any(
                    item in {"nascs", "nasc", "nes", "ns"} or _similar(item, "nascs")
                    for item in recent
                )
            )
            if not (sign_like or noise_like):
                continue

            start_index = index - 1
            while start_index >= 0 and index - start_index <= 4:
                item = _fold(tokens[start_index].group())
                if (item in _PUNCT_MARKERS or item in _PUNCT_NOISE
                        or item in _PUNCT_FILLER or item in _PUNCT_OFF
                        or _similar(item, "signes")):
                    start_index -= 1
                else:
                    break

            start = tokens[start_index + 1].start()
            end = token.end()
            tail = re.match(r"[ \t]*[,.;:!?…]*", text[end:])
            end += tail.end() if tail else 0
            is_off = any(item in _PUNCT_OFF for item in previous)
            return start, end, is_off
        return None

    # ---- deletreig ----

    def _letter_phrase(self, text: str) -> str:
        """Converteix "la lletra essa" -> "la lletra S": quan l'usuari demana
        expressament una lletra, s'escriu la lletra, no el nom.

        El model sovint introdueix ompliments ("la lletra, a, essa") o encadena
        frases ("la lletra essa i la lletra u"). Es mira una finestra curta de
        paraules i es tria el nom de lletra mes plausible: primer els noms
        distintius (essa, erre...), i si no n'hi ha, els ambigus (a, e, u...)."""
        if not self.spelling_auto and not self.spelling_mode:
            return text
        prefixes = "|".join(
            r"[\s,;]+".join(re.escape(part) for part in prefix.split())
            for prefix in LETTER_PHRASES
        )
        pattern = re.compile(
            rf"(?<!\w)(?P<prefix>{prefixes})[,;\s]+"
            rf"((?:[^\W\d_]+[,;\s]+){{0,2}}[^\W\d_]+)",
            re.IGNORECASE,
        )
        out: list[str] = []
        pos = 0
        while True:
            match = pattern.search(text, pos)
            if match is None:
                out.append(text[pos:])
                break
            word_matches = list(
                WORD_RE.finditer(text, match.start(2), match.end(2))
            )
            first = word_matches[0].group(0)
            first_key = first.lower()
            # Si la paraula ja es una lletra ("la lletra S"), no busquem mes
            # enlla: si no, ens menjariem el "i" de la frase seguent.
            if (len(first) == 1 and first.isascii() and first.isalpha()
                    and (first.isupper() or first_key not in LETTERS)):
                out.append(text[pos:word_matches[0].end()])
                pos = word_matches[0].end()
                continue
            words = [word.group(0) for word in word_matches]
            strong: tuple[int, int, str] | None = None
            weak: tuple[int, int, str] | None = None
            for start in range(len(words)):
                for size in (2, 1):
                    if start + size > len(words):
                        continue
                    key = " ".join(words[start:start + size]).lower()
                    letter = LETTERS.get(key)
                    if letter is None:
                        continue
                    candidate = (start, size, letter)
                    if self._is_strong(key):
                        if strong is None:
                            strong = candidate
                    elif weak is None:
                        weak = candidate
                    break
            chosen = strong or weak
            if chosen is None:
                out.append(text[pos:match.end()])
                pos = match.end()
                continue
            start, size, letter = chosen
            if not self.spelling_uppercase:
                letter = letter.lower()
            out.append(text[pos:match.start()])
            out.append(f"{match.group('prefix')} {letter}")
            # Continuem just despres del nom triat, per no menjar-nos la
            # frase seguent ("... essa i la lletra u").
            pos = word_matches[start + size - 1].end()
        return "".join(out)

    def _is_strong(self, name: str) -> bool:
        return len(name) > 1 and name not in WEAK_NAMES

    def _spell(self, text: str) -> str:
        names = LETTERS if self.spelling_mode else {
            key: value for key, value in LETTERS.items()
            if key in CATALAN_LETTERS or key in SPANISH_LETTERS
        }
        if not self.spelling_mode and not self.spelling_auto:
            return text

        words = list(WORD_RE.finditer(text))
        runs: list[dict] = []
        current: dict | None = None

        def close() -> None:
            nonlocal current
            if current is not None:
                runs.append(current)
                current = None

        index = 0
        while index < len(words):
            match = words[index]
            key = match.group(0).lower()
            consumed = 1

            # Noms de dues o tres paraules ("doble ve", "i grega", "ela geminada").
            if index + 1 < len(words):
                gap = text[match.end():words[index + 1].start()]
                candidate = f"{key} {words[index + 1].group(0).lower()}"
                if candidate in names and not gap.strip():
                    key = candidate
                    consumed = 2
                    if index + 2 < len(words):
                        gap2 = text[words[index + 1].end():words[index + 2].start()]
                        candidate3 = f"{key} {words[index + 2].group(0).lower()}"
                        if candidate3 in names and not gap2.strip():
                            key = candidate3
                            consumed = 3

            end_match = words[index + consumed - 1]
            if key in names:
                letter = names[key]
                strong = self._is_strong(key)
            elif len(key) == 1 and key.isascii() and key.isalpha():
                # Whisper de vegades ja retorna les lletres separades ("S C F F").
                letter = key.upper() if self.spelling_uppercase else key.lower()
                strong = key.upper() not in "AEIOU"
            else:
                close()
                index += 1
                continue

            if not self.spelling_uppercase:
                letter = letter.lower()

            if current is None:
                current = {
                    "start": match.start(),
                    "end": end_match.end(),
                    "letters": [letter],
                    "strong": 1 if strong else 0,
                }
            else:
                gap = text[current["end"]:match.start()]
                if GAP_RE.fullmatch(gap):
                    current["end"] = end_match.end()
                    current["letters"].append(letter)
                    if strong:
                        current["strong"] += 1
                else:
                    close()
                    current = {
                        "start": match.start(),
                        "end": end_match.end(),
                        "letters": [letter],
                        "strong": 1 if strong else 0,
                    }
            index += consumed

        close()

        for run in reversed(runs):
            count = len(run["letters"])
            qualifies = self.spelling_mode or (count >= 3 and run["strong"] >= 2)
            if not qualifies:
                continue
            joined = self.separator.join(run["letters"])
            text = text[:run["start"]] + joined + text[run["end"]:]

        # Un sol nom distintiu ("efa", "essa") tambe es converteix. Els noms
        # ambigus no, perque son paraules normals.
        if not self.spelling_mode:
            core = text.strip(" \t.,;:!?…")
            key = core.lower()
            if key in SAFE_SINGLE and key in LETTERS:
                start = text.index(core)
                end = start + len(core)
                letter = LETTERS[key]
                if not self.spelling_uppercase:
                    letter = letter.lower()
                text = text[:start] + letter + text[end:]

        return text

    # ---- puntuacio ----

    def _punctuate(self, text: str) -> str:
        for phrase in sorted(PUNCTUATION, key=len, reverse=True):
            symbol = PUNCTUATION[phrase]
            text = _phrase_pattern(phrase).sub(lambda _m, s=symbol: s, text)
        return self._tidy(text)

    @staticmethod
    def _tidy(text: str) -> str:
        text = re.sub(r"[ \t]+([,.;:!?%\)\]\}])", r"\1", text)
        text = re.sub(r"([\(\[])[ \t]+", r"\1", text)
        text = re.sub(
            r"(?<=\w)\s+\.(com|cat|org|net|eu|es|edu|gov|info|io|dev|app)\b",
            r".\1", text, flags=re.IGNORECASE,
        )
        text = re.sub(r"\s*/\s*", "/", text)
        text = re.sub(r"\s*@\s*", "@", text)
        text = re.sub(r",\s+(?=\d)", ",", text)
        text = re.sub(r"([,;:!?])(?=[^\s\d])", r"\1 ", text)
        text = re.sub(r"([,;:!?])\1+", r"\1", text)
        text = re.sub(r"([,;:!?])\s*\.(?!\.\.)", r"\1", text)
        text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
        text = re.sub(r"\.{4,}", "...", text)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
