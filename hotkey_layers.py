"""A gyorsgombok rétegei: az alap (preset-, ciklus-, overlay-gombok) fölé az overlay, a menü és a térkép a saját, ideiglenes
billentyűit teszi. Az operációs rendszer felé mindig az összeg megy, így az egyik réteg állapotváltása (például a térkép
leállása) nem szabadítja fel a másik, még nyitott réteg gombjait."""


class HotkeyLayers:
    """`base()`: az alap gyorsgomb-térkép; `apply(mapping)`: a teljes térkép cseréje a gyorsgomb-szálban. Egy réteg gombjai
    azok a nevek, amelyek nincsenek az alapban; a réteg az alapot is tartalmazó térképpel hívja a `setter(owner)` függvényét."""

    def __init__(self, base, apply):
        self._base, self._apply, self._layers = base, apply, {}

    def setter(self, owner):
        return lambda mapping: self._set(owner, mapping)

    def refresh(self):
        merged = dict(self._base())
        for layer in self._layers.values():
            merged.update(layer)
        self._apply(merged)

    def _set(self, owner, mapping):
        base = self._base()
        self._layers[owner] = {name: spec for name, spec in mapping.items() if name not in base}
        self.refresh()
