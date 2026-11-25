"""Event tree: the initiating event's frequency and each heading's branch probability in; each end state's
frequency (or probability, with no initiating frequency) out.

A heading can have a different probability on each branch it is asked on (``given`` earlier answers), so
each probability is an input of its own, its cell naming the branch (``event_tree:probability:<given>``,
the address uncertainty ranges use). Monte Carlo (``risk_uncertainty``) samples through the same
:meth:`EventTreePredictor.evaluate`.
"""

from __future__ import annotations

from typing import Any

from latris.operations.predictors import Candidate, Run, key

FREQUENCY = "event_tree:frequency"
PER_YEAR = "1/year"


def probability_cell(given) -> str:  # noqa: ANN001 — (heading, answer) pairs
    """The cell of a heading's probability on the branch ``given``."""
    given_key = ",".join(f"{h}={a}" for h, a in sorted(given))
    return "event_tree:probability" + (f":{given_key}" if given_key else "")


class EventTreePredictor:
    def __init__(self, paths) -> None:  # noqa: ANN001
        from latris.operations import event_tree as et

        self.tree = tree = et.load_tree(root=paths.root)
        self.labels = lab = tree.labels
        self.problems: list[str] = []
        self.point: dict[str, float] = {}  # input key → the model's own value
        self.input_labels: dict[str, str] = {}
        self.headings: dict[str, str] = {}  # input key → the heading it is a probability of
        self.seqs: list[tuple[str, list[tuple[str, str]]]] = []  # (end state id, [(input key, answer)])
        self.ends: list[str] = []
        self.fkey: str | None = None
        if tree.problems:
            self.problems = ["the event tree is incomplete; `latris et check` lists what's missing"]
            return
        payload = et.analyse(root=paths.root)
        if not payload["quantified"]:
            self.problems = [f"the event tree isn't quantified yet (missing: {'; '.join(payload['missing'])})"]
            return
        for q in tree.structure.sequences:
            prefix: list[tuple[str, str]] = []
            factors: list[tuple[str, str]] = []
            for s in q.path:
                e = et._lookup(tree, s.heading, prefix)
                k = key(e.target_id, probability_cell((c.heading, c.answer) for c in e.given))  # type: ignore[union-attr]
                self.point[k] = e.p_yes  # type: ignore[union-attr]
                self.headings[k] = s.heading
                given = tree.answer_text([(c.heading, c.answer) for c in e.given]) if e.given else ""  # type: ignore[union-attr]
                self.input_labels[k] = f"P({lab[s.heading]}=yes" + (f" | {given})" if given else ")")
                factors.append((k, s.answer))
                prefix.append((s.heading, s.answer))
            self.seqs.append((q.end_state, factors))
        f = tree.frequency
        if f is not None:
            self.fkey = key(f.target_id, FREQUENCY)
            self.point[self.fkey] = f.frequency
            self.input_labels[self.fkey] = f"{lab[f.target_id]} (frequency)"
        self.ends = list(dict.fromkeys(end for end, _ in self.seqs))

    @property
    def units(self) -> str:
        return PER_YEAR if self.fkey else "dimensionless"

    def inputs(self) -> list[Candidate]:
        out = []
        if self.fkey:
            out.append(Candidate(self.tree.frequency.target_id, self.input_labels[self.fkey], ("value",),  # type: ignore[union-attr]
                                 units=PER_YEAR, value=self.point[self.fkey], valid_min=0.0,
                                 role="initiating event (frequency)", suggested=True, cell=FREQUENCY, exact=True))
        for k in sorted((k for k in self.point if k != self.fkey), key=lambda k: self.input_labels[k].casefold()):
            out.append(Candidate(self.headings[k], self.input_labels[k], ("value",), units="dimensionless",
                                 value=self.point[k], valid_min=0.0, valid_max=1.0, role="heading (probability of yes)",
                                 suggested=True, cell=k.split("|", 1)[1], exact=True))
        return out

    def outputs(self) -> list[Candidate]:
        if not self.ends:
            return []
        point = self.evaluate(self.point)
        rarest = min(self.ends, key=lambda n: (point[n], self.labels[n]))  # the usual concern: the rare, bad one
        what = "frequency" if self.fkey else "probability"
        return [Candidate(e, self.labels[e], ("value",), units=self.units, role=f"end state ({what})",
                          suggested=e == rarest) for e in sorted(self.ends, key=lambda e: self.labels[e].casefold())]

    def evaluate(self, x: dict[str, float]) -> dict[str, float]:
        """Each end state's frequency (or probability), by entity id, from every input by key."""
        out = dict.fromkeys(self.ends, 0.0)
        for end, factors in self.seqs:
            p = 1.0
            for k, ans in factors:
                p *= x[k] if ans == "yes" else 1.0 - x[k]
            out[end] += p
        scale = x[self.fkey] if self.fkey else 1.0
        return {n: v * scale for n, v in out.items()}

    def run(self, values: dict[str, Any], modes: dict[str, str], outputs: list[Any]) -> Run:
        got = self.evaluate({**self.point, **{k: float(v) for k, v in values.items()}})
        return Run({o.name: got[o.target_id] for o in outputs})


def build(paths) -> EventTreePredictor:  # noqa: ANN001
    return EventTreePredictor(paths)
