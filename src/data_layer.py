import json
import pathlib


class DataLayer:
    def __init__(self, data_dir: str):
        d = pathlib.Path(data_dir)
        self._items: dict = json.loads((d / "items.json").read_text())
        recipes: list = json.loads((d / "recipes.json").read_text())
        bundles: list = json.loads((d / "bundles.json").read_text())
        self._gifts: dict = json.loads((d / "gifts.json").read_text())

        self._used_in: dict[str, list] = {}
        self._crafted_from: dict[str, list] = {}
        for r in recipes:
            ref = {"recipeId": r["id"], "name": r["name"], "yields": r["yields"]}
            for ing in r["ingredients"]:
                self._used_in.setdefault(ing["item"], []).append(ref)
            # Resolve ingredient names so the C# side doesn't need a second lookup
            resolved = [
                {"name": self._items.get(ing["item"], {}).get("name", ing["item"]), "count": ing["count"]}
                for ing in r["ingredients"]
            ]
            self._crafted_from[r["yields"]] = resolved

        self._in_bundles: dict[str, list] = {}
        for b in bundles:
            ref = {"bundleId": b["id"], "room": b["room"], "name": b["name"]}
            for slot in b["items"]:
                self._in_bundles.setdefault(slot["item"], []).append(ref)

    @property
    def count(self) -> int:
        return len(self._items)

    def get(self, qualified_id: str):
        item = self._items.get(qualified_id)
        if item is None:
            return None
        return {
            **item,
            "craftedFrom": self._crafted_from.get(qualified_id, []),
            "craftingUses": self._used_in.get(qualified_id, []),
            "bundles": self._in_bundles.get(qualified_id, []),
            "gifts": self._gifts.get(
                qualified_id,
                {"loves": [], "likes": [], "neutrals": [], "dislikes": [], "hates": []},
            ),
        }
