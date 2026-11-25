"""Bow-tie: threats' frequencies, barriers' failure probabilities and status in; the top event's and each
consequence's frequency out (the layer-of-protection estimate, ``bow_tie._frequencies``).

A barrier's status is an input of its own (a state): a caller can ask "what if this barrier is out?"
without knowing its PFD — ``not_in_place`` fails it every time (PFD 1), as the analysis does. Monte Carlo
(``risk_uncertainty``) samples through the same :meth:`BowTiePredictor.evaluate`.
"""

from __future__ import annotations

from typing import Any

from latris.operations.predictors import Candidate, Run, key, split_key

FREQUENCY, PFD, STATUS = "bow_tie:frequency", "bow_tie:pfd", "bow_tie:status"
STATUSES = ("in_place", "degraded", "not_in_place")
PER_YEAR = "1/year"


class BowTiePredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        from latris.operations import bow_tie as bt_ops

        self._ops = bt_ops
        self.bt = bt = bt_ops.load_bow_tie(root=paths.root)
        self.labels = bt.labels
        self.problems: list[str] = []
        self.threats: list[str] = []
        self.on_lines: list[str] = []
        self.point: dict[str, float] = {}  # numeric input key → the model's own value
        self.fixed_pfd: dict[str, float] = {}  # barriers not in place: they fail every time
        if bt.problems:
            self.problems = ["the bow-tie is incomplete; `latris bowtie analyse` lists what's missing"]
            return
        payload = bt_ops.analyse(root=paths.root)
        if not payload["quantified"]:
            self.problems = [f"the bow-tie isn't quantified yet (missing: {', '.join(payload['missing'])})"]
        self.threats = sorted({ln.start for ln in bt.left}, key=lambda t: self.labels[t].casefold())
        self.on_lines = sorted({b for ln in bt.left + bt.right for b in ln.barriers},
                               key=lambda b: self.labels[b].casefold())
        for b in self.on_lines:
            entry = bt.barriers.get(b)
            if entry is not None and entry.status == "not_in_place":
                self.fixed_pfd[b] = 1.0
            elif entry is not None and entry.pfd is not None:
                self.point[key(b, PFD)] = entry.pfd
        for t in self.threats:
            if t in bt.frequencies:
                self.point[key(t, FREQUENCY)] = bt.frequencies[t].frequency

    def _status(self, b: str) -> str:
        entry = self.bt.barriers.get(b)
        return entry.status if entry else "in_place"

    def inputs(self) -> list[Candidate]:
        bt = self.bt
        out = [Candidate(t, f"{self.labels[t]} (frequency)", ("value",), units=PER_YEAR,
                         value=bt.frequencies[t].frequency if t in bt.frequencies else None, valid_min=0.0,
                         role="threat (frequency)", suggested=True, cell=FREQUENCY, exact=True)
               for t in self.threats]
        for b in self.on_lines:
            entry = bt.barriers.get(b)
            out.append(Candidate(b, f"{self.labels[b]} (PFD)", ("value",), units="dimensionless",
                                 value=entry.pfd if entry else None, valid_min=0.0, valid_max=1.0,
                                 role="barrier (probability of failure on demand)", suggested=True, cell=PFD,
                                 exact=True))
            out.append(Candidate(b, f"{self.labels[b]} (status)", ("state",), states=STATUSES, value=self._status(b),
                                 role="barrier (status)", cell=STATUS))
        return out

    def outputs(self) -> list[Candidate]:
        bt = self.bt
        if bt.problems or bt.top is None:
            return []
        cons = sorted({ln.end for ln in bt.right}, key=lambda c: self.labels[c].casefold())
        return [Candidate(bt.top, self.labels[bt.top], ("value",), units=PER_YEAR, role="top event (frequency)",
                          suggested=True),
                *(Candidate(c, self.labels[c], ("value",), units=PER_YEAR, role="consequence (frequency)",
                            suggested=True) for c in cons)]

    def evaluate(self, x: dict[str, float], status: dict[str, str] | None = None) -> dict[str, float]:
        """The top event's and each consequence's frequency (by entity id), from every threat's frequency and
        barrier's PFD (by input key); ``status`` (barrier id → status) overrides the model's."""
        pfd: dict[str, float] = dict(self.fixed_pfd)
        freq: dict[str, float] = {}
        for k, v in x.items():
            node, cell = split_key(k)
            (pfd if cell == PFD else freq)[node] = v
        for b, s in (status or {}).items():
            if s == "not_in_place":
                pfd[b] = 1.0
            elif b in self.fixed_pfd:  # back in place: it needs a PFD of its own
                entry = self.bt.barriers.get(b)
                given = x.get(key(b, PFD), entry.pfd if entry else None)
                if given is None:
                    raise ValueError(f"{self.labels[b]} is not in place in the model, so it has no failure "
                                     "probability: give its PFD too")
                pfd[b] = given
        f_top, f_cons = self._ops._frequencies(self.bt, pfd, freq)
        return {self.bt.top: f_top, **f_cons}  # type: ignore[dict-item]

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        status = {split_key(k)[0]: str(v) for k, v in values.items() if split_key(k)[1] == STATUS}
        for s in status.values():
            if s not in STATUSES:
                raise ValueError(f"{s!r} is not a barrier status (one of: {', '.join(STATUSES)})")
        numbers = {k: float(v) for k, v in values.items() if split_key(k)[1] != STATUS}
        got = self.evaluate({**self.point, **numbers}, status)
        return Run({o.name: got[o.target_id] for o in outputs})


def build(paths) -> BowTiePredictor:  # noqa: ANN001
    return BowTiePredictor(paths)
