"""time_sensitivity.py: the claim in its docstring - at the locked theta the time factor cannot change a decision."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gate.trust_gate import GateParams, decide_candidate  # noqa: E402
from time_sensitivity import day  # noqa: E402

LOCKED = -0.05
AGES = (0, 30, 365, 3650)
LAMBDAS = (0.0, 0.001, 0.01)


def sig(c_content, r, age):
    return {"t_source": 0.9, "c_content": c_content, "r_contradiction": r, "r_pattern": 0.0, "age_days": age}


def decision(s, theta, lam):
    return decide_candidate(s, GateParams(theta_accept=theta, theta_reject=theta, lambda_r=1.0, lambda_t=lam))[1]


def test_locked_theta_time_never_changes_decision():
    for c in (0.0, 0.5, 1.0):
        for age in AGES:
            for lam in LAMBDAS:
                assert decision(sig(c, 0.0, age), LOCKED, lam) == "accept"   # R = 0 -> score >= 0 > theta
                assert decision(sig(c, 1.0, age), LOCKED, lam) == "reject"   # R = 1 -> score <= -0.1 < theta


def test_stricter_theta_time_can_change_decision():
    s_new, s_old = sig(1.0, 0.0, 0), sig(1.0, 0.0, 365)
    assert decision(s_new, 0.3, 0.01) == "accept"      # 0.9 * 1 >= 0.3
    assert decision(s_old, 0.3, 0.01) == "reject"      # 0.9 * exp(-3.65) ~ 0.02 < 0.3
    assert decision(s_old, 0.3, 0.0) == "accept"       # lambda_t = 0 -> no decay


def test_day_parses_longmemeval_dates():
    assert (day("2023/05/30 (Tue) 23:40") - day("2023/05/20 (Sat) 02:21")).days == 10
