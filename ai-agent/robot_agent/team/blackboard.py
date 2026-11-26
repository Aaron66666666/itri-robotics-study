"""Shared message board: every message between agents is recorded, in order,
so a run can be replayed and audited afterwards."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field


@dataclass
class Note:
    seq: int
    t: float
    sender: str
    to: str
    kind: str          # observation | prediction | decision | action | result | refusal | report
    content: dict


@dataclass
class Blackboard:
    notes: list[Note] = field(default_factory=list)
    t0: float = field(default_factory=time.monotonic)

    def post(self, sender: str, to: str, kind: str, content: dict) -> Note:
        note = Note(len(self.notes) + 1, round(time.monotonic() - self.t0, 2), sender, to, kind, content)
        self.notes.append(note)
        return note

    def last(self, kind: str, sender: str | None = None) -> Note | None:
        for n in reversed(self.notes):
            if n.kind == kind and (sender is None or n.sender == sender):
                return n
        return None

    def to_json(self) -> str:
        return json.dumps([asdict(n) for n in self.notes], ensure_ascii=False, indent=1)

    def transcript(self) -> str:
        """Human-readable log: one line per message."""
        lines = []
        for n in self.notes:
            body = json.dumps(n.content, ensure_ascii=False)
            lines.append(f"[{n.seq:02d} +{n.t:6.1f}s] {n.sender:>10} -> {n.to:<10} {n.kind:<11} {body[:180]}")
        return "\n".join(lines)
