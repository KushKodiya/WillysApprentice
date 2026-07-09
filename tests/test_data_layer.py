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
    assert any(b["bundleId"] == "fish_tank_10" for b in item["bundles"])
    assert "Abigail" in item["gifts"]["loves"]
    assert "Harvey" in item["gifts"]["dislikes"]


def test_item_no_crafting_uses():
    d = _layer()
    item = d.get("(O)128")  # Pufferfish — not an ingredient in any recipe
    assert item is not None
    assert item["craftingUses"] == []


def test_crafted_from():
    d = _layer()
    item = d.get("(O)322")  # Wood Fence — crafted from Wood x2
    assert item is not None
    assert item["craftedFrom"] == [{"name": "Wood", "count": 2}]


def test_miss_returns_none():
    assert _layer().get("(O)9999") is None


def test_count():
    assert _layer().count == 2199


def test_gifts_for_blueberry():
    d = _layer()
    item = d.get("(O)258")
    assert item is not None
    assert "Leah" in item["gifts"]["likes"]
