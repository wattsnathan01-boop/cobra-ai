"""Turn a streamed reply into speakable sentences, as soon as each one is complete."""
from __future__ import annotations

import re

# a sentence ends at . ! ? … (plus closing quotes/brackets) followed by whitespace, or at a newline
_END = re.compile(r"(?<=[.!?…])[\"')\]]*\s+|\n+")
_MARKUP = re.compile(r"[*_`#>|~]+")
_SPACES = re.compile(r"\s+")
# no punctuation for this long: break at a comma or space so speech doesn't stall
_MAX_CHARS = 220


def clean_for_speech(text: str) -> str:
    """Strip markdown symbols and odd spacing that a TTS would read out or stumble on."""
    text = _MARKUP.sub(" ", text)
    text = text.replace("°C", " degrees").replace("°", " degrees")
    return _SPACES.sub(" ", text).strip()


class SentenceSplitter:
    def __init__(self) -> None:
        self.buf = ""

    def feed(self, text: str) -> list[str]:
        """Add streamed text; return any sentences that are now complete."""
        self.buf += text
        out = []
        while True:
            m = _END.search(self.buf)
            if not m:
                break
            out.append(self.buf[:m.end()])
            self.buf = self.buf[m.end():]
        while len(self.buf) > _MAX_CHARS:
            cut = self.buf.rfind(", ", 0, _MAX_CHARS)
            cut = cut + 1 if cut > 0 else self.buf.rfind(" ", 0, _MAX_CHARS)
            if cut <= 0:
                cut = _MAX_CHARS
            out.append(self.buf[:cut])
            self.buf = self.buf[cut:]
        return [s for s in (clean_for_speech(s) for s in out) if s]

    def flush(self) -> list[str]:
        """The reply has finished: return whatever is left."""
        rest, self.buf = clean_for_speech(self.buf), ""
        return [rest] if rest else []
