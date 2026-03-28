"""
Aureon Engine — Completeness Engine
Shared scoring engine. In onboarding: document completeness.
In transformation: taxonomy mapping + workstream readiness.
Same math, same thresholds, same gate triggers. Different items.
"""

from dataclasses import dataclass, field
from enum import Enum


class ItemStatus(str, Enum):
    PRESENT    = "present"
    MISSING    = "missing"
    DERIVABLE  = "derivable"
    FLAGGED    = "flagged"     # present but needs human review


class ScoreThreshold(str, Enum):
    COMPLETE    = "complete"    # 100%
    IN_PROGRESS = "in_progress" # 75-99%
    INCOMPLETE  = "incomplete"  # 50-74%
    CRITICAL    = "critical"    # <50%


@dataclass
class CompletenessItem:
    id:          str
    name:        str
    category:    str
    status:      ItemStatus = ItemStatus.MISSING
    confidence:  float = 0.0
    gate_trigger: str = ""      # which HITL gate this item can trigger
    note:        str = ""


@dataclass
class CompletenessRecord:
    case_id:    str
    practice:   str
    items:      list[CompletenessItem] = field(default_factory=list)

    @property
    def score(self) -> int:
        if not self.items:
            return 0
        present = sum(1 for i in self.items
                      if i.status in (ItemStatus.PRESENT, ItemStatus.DERIVABLE))
        return round(present / len(self.items) * 100)

    @property
    def threshold(self) -> ScoreThreshold:
        s = self.score
        if s == 100:  return ScoreThreshold.COMPLETE
        if s >= 75:   return ScoreThreshold.IN_PROGRESS
        if s >= 50:   return ScoreThreshold.INCOMPLETE
        return ScoreThreshold.CRITICAL

    @property
    def missing(self) -> list[CompletenessItem]:
        return [i for i in self.items if i.status == ItemStatus.MISSING]

    @property
    def flagged(self) -> list[CompletenessItem]:
        return [i for i in self.items if i.status == ItemStatus.FLAGGED]

    @property
    def present(self) -> list[CompletenessItem]:
        return [i for i in self.items
                if i.status in (ItemStatus.PRESENT, ItemStatus.DERIVABLE)]

    def summary(self) -> dict:
        return {
            "score":      self.score,
            "threshold":  self.threshold.value,
            "total":      len(self.items),
            "present":    len(self.present),
            "missing":    len(self.missing),
            "flagged":    len(self.flagged),
            "gate_5_ready": self.score == 100 and len(self.flagged) == 0,
        }

    def to_dict(self) -> dict:
        return {
            "case_id":  self.case_id,
            "practice": self.practice,
            "summary":  self.summary(),
            "items": [
                {
                    "id":         i.id,
                    "name":       i.name,
                    "category":   i.category,
                    "status":     i.status.value,
                    "confidence": round(i.confidence * 100),
                    "note":       i.note,
                }
                for i in self.items
            ]
        }


# ── CONFIDENCE THRESHOLDS (shared doctrine) ────────────────────────────
AUTO_THRESHOLD    = 0.85   # ≥85% → auto-classified, no HITL needed
REVIEW_THRESHOLD  = 0.60   # 60-84% → HITL-3 review required
REJECT_THRESHOLD  = 0.60   # <60% → rejected, returned to client

def classify_confidence(score: float) -> ItemStatus:
    if score >= AUTO_THRESHOLD:   return ItemStatus.PRESENT
    if score >= REVIEW_THRESHOLD: return ItemStatus.FLAGGED
    return ItemStatus.MISSING
