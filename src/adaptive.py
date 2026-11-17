"""
adaptive.py — inserts an adaptive-attack case (data/adaptive_cases.json) into LoCoMo sessions.

Separate from locomo.inject_poison() so the locked injection code stays untouched. A case carries one or more
`inserts`, each a list of dialog turns appended to the END of the given session (in order).
Labels (attack, poison_keys, ...) are never inserted; the writer only sees the turn text.
"""
import copy


def inject_adaptive(sessions, case):
    out = copy.deepcopy(sessions)
    by_num = {s["session"]: s for s in out}
    for ins in case["inserts"]:
        target = by_num.get(ins["session"])
        if target is None or target["sample_id"] != case["sample_id"]:
            raise ValueError(f"{case['case_id']}: session {ins['session']} not found in {case['sample_id']}")
        target["turns"].extend(dict(t) for t in ins["turns"])
    return out
