"""Mapa de tempo ORIGINAL (pre-corte) -> NOVO (pos-jumpcut), core.render.jumpcut.

Um clipe editado por jump-cut vira uma sequencia de trechos MANTIDOS (tempo
LOCAL original do clip); o tempo NOVO de cada trecho e a soma cumulativa das
duracoes dos trechos anteriores (os buracos entre eles = trechos removidos,
descartados do somatorio). Usado tanto pelo proprio render (posiciona os
pedacos no filtro de video/audio) quanto para remapear legendas pelo mesmo
corte (tempo original de uma palavra -> onde ela cai no video ja cortado)."""


class TimeMap:
    def __init__(self, segments: list[dict]):
        """`segments`: [{start, end}] em tempo LOCAL ORIGINAL do clip,
        ordenados, SEM overlap (buracos entre eles = trechos removidos)."""
        self.segments = sorted(segments, key=lambda s: s["start"])
        self._new_start: list[float] = []
        t = 0.0
        for s in self.segments:
            self._new_start.append(t)
            t += s["end"] - s["start"]
        self.new_duration = t

    def to_new(self, orig_t: float) -> float | None:
        """Posicao no tempo NOVO (pos-corte), ou None se `orig_t` cai dentro
        de um trecho removido."""
        for seg, base in zip(self.segments, self._new_start):
            if seg["start"] <= orig_t <= seg["end"]:
                return base + (orig_t - seg["start"])
        return None

    def clamp_to_new(self, orig_t: float) -> float:
        """Como `to_new`, mas nunca None: cai dentro de um buraco -> usa a
        borda do trecho mantido mais proximo (jump-cut so corta ENTRE
        palavras, entao isso so importa em bordas exatas/arredondamento)."""
        mapped = self.to_new(orig_t)
        if mapped is not None:
            return mapped
        if not self.segments:
            return 0.0
        before = [(s, b) for s, b in zip(self.segments, self._new_start) if s["end"] <= orig_t]
        after = [(s, b) for s, b in zip(self.segments, self._new_start) if s["start"] >= orig_t]
        if before:
            s, b = before[-1]
            return b + (s["end"] - s["start"])
        if after:
            return after[0][1]
        return self.new_duration
