import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.data_layer import DataLayer

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"


def _layer():
    return DataLayer(str(_DATA_DIR))


def test_item_with_all_data():
    d = _layer()
    item = d.get("(O)128")
    assert item is not None
    assert item["name"] == "Pufferfish"
    assert any(r["recipeId"] == "maki_roll" for r in item["craftingUses"])
    assert any(r["recipeId"] == "sashimi" for r in item["craftingUses"])
    assert any(b["bundleId"] == "ocean_fish" for b in item["bundles"])
    assert "Sebastian" in item["gifts"]["loves"]
    assert "Abigail" in item["gifts"]["dislikes"]


def test_item_no_crafting_uses():
    d = _layer()
    item = d.get("(O)16")
    assert item is not None
    assert item["craftingUses"] == []
    assert any(b["bundleId"] == "spring_foraging" for b in item["bundles"])


def test_big_craftable_no_extras():
    d = _layer()
    item = d.get("(BC)15")
    assert item is not None
    assert item["name"] == "Chest"
    assert item["craftingUses"] == []
    assert item["bundles"] == []
    assert item["gifts"]["loves"] == []


def test_miss_returns_none():
    assert _layer().get("(O)9999") is None


def test_count():
    assert _layer().count == 4


def test_gifts_fallback_for_unknown_id():
    d = _layer()
    item = d.get("(O)258")
    assert item is not None
    assert "Leah" in item["gifts"]["likes"]
