"""Tests for answer normalization. Run: pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from textnorm import contains_any, normalize  # noqa: E402


def test_normalize():
    assert normalize("The 'Guinea Pig'!") == "guinea pig"
    assert normalize("a hamster") == "hamster"
    assert normalize("Chicken   Pot-Pie") == "chicken pot pie"


def test_contains_any_whole_words():
    assert contains_any("She has a guinea pig.", ["guinea pig"])
    assert contains_any("Her grandma is from Norway.", ["Norway", "Norwegian"])
    assert not contains_any("Caroline is Swedish", ["Swede"])  # not a partial word
    assert not contains_any("anything", ["the"])  # keys that normalize to nothing are ignored
