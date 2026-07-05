"""
Transform raw Content Patcher exports into the project's wiki data schema.

Place the five CP exports in --raw-dir (default: data/raw/):
  Objects.json         <-- patch export Data/Objects
  CraftingRecipes.json <-- patch export Data/CraftingRecipes
  CookingRecipes.json  <-- patch export Data/CookingRecipes
  Bundles.json         <-- patch export Data/Bundles
  NPCGiftTastes.json   <-- patch export Data/NPCGiftTastes
  StringsObjects.json  <-- patch export Strings/Objects  (optional; resolves DisplayName tokens)

By default, prints 5 samples per file and exits.
Pass --write to overwrite data/*.json.

Usage:
  python src/tools/build_data_dump.py --raw-dir data/raw
  python src/tools/build_data_dump.py --raw-dir data/raw --write --out-dir data
  python src/tools/build_data_dump.py --raw-dir data/raw --sample 10

FORMAT ASSUMPTIONS (SV 1.6, CP export):
  Objects:        dict keyed by item id (legacy int string or qualified "(O)N")
                  Each value: {"Name", "DisplayName", "Description", "Type",
                               "Price", "Edibility", "Category", ...}
                  DisplayName/Description may be "[LocalizedText Strings\\Objects:Key]"
                  tokens; resolved via StringsObjects.json if present, else falls back
                  to internal Name field.
  CraftingRecipes: dict of name -> "ingredients/unused/[type/]result_id[ count]/false/source"
                  result slot may be "id" or "id count" space-separated
  CookingRecipes:  dict of name -> "ingredients/unused_or_cond/result_id/count[/source]"
  Bundles:         dict of "Area/bundle_id" -> "name/reward/items/color[/...]"
                   reward: "O item_id count" or "BO item_id count"
                            (letter prefix: O=Object, BO=BigCraftable)
                   items:  "itemId count quality itemId count quality ..."
                   -- OR in 1.6, values may be BundleData objects; see _parse_bundle()
  NPCGiftTastes:   dict of NPC name -> slash-delimited:
                   "love_text/love_ids/like_text/like_ids/dislike_text/dislike_ids/
                    hate_text/hate_ids[/neutral_ids]"
                   where ids are space-separated item id strings; negative ids are
                   category codes and are expanded to all items in that category.
"""
import argparse
import json
import pathlib
import sys
from collections import defaultdict


# --- Helpers ------------------------------------------------------------------

def qualify(item_id: str, *, bc: bool = False) -> str:
    """Add (O) or (BC) prefix if the ID isn't already qualified."""
    s = str(item_id).strip()
    if s.startswith("(") or s == "-1":
        return s
    return f"(BC){s}" if bc else f"(O){s}"


def _load(raw_dir: pathlib.Path, filename: str) -> dict:
    path = raw_dir / filename
    if not path.exists():
        sys.exit(f"Missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_strings(raw_dir: pathlib.Path) -> dict:
    """Load StringsObjects.json if present; returns {} if missing (graceful degradation)."""
    path = raw_dir / "StringsObjects.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


_LOCTEXT_PREFIX = "[LocalizedText Strings\\Objects:"

def _resolve_text(value: str, strings: dict) -> str:
    """Resolve [LocalizedText Strings\\Objects:Key] tokens; return value unchanged if not a token."""
    if not value.startswith(_LOCTEXT_PREFIX):
        return value
    key = value[len(_LOCTEXT_PREFIX):].rstrip("]")
    return strings.get(key, value)  # leave token in place if key missing (visible in output)


# --- Items --------------------------------------------------------------------

def transform_items(raw: dict, strings: dict) -> dict:
    out = {}
    for item_id, obj in raw.items():
        qid = qualify(item_id)
        legacy_id = int(item_id) if str(item_id).isdigit() else None
        edibility = obj.get("Edibility", -300)
        is_edible = edibility != -300
        # Category: use human-readable Type string (e.g. "Fish", "Vegetable")
        category = obj.get("Type") or str(obj.get("Category", ""))
        # Prefer resolved DisplayName over internal Name; fall back to Name if token unresolved
        raw_display = obj.get("DisplayName") or obj.get("Name", "")
        name = _resolve_text(raw_display, strings)
        if name.startswith("[LocalizedText"):  # strings file missing or key absent
            name = obj.get("Name", raw_display)
        raw_desc = obj.get("Description", "")
        description = _resolve_text(raw_desc, strings)
        if description.startswith("[LocalizedText"):
            description = ""
        out[qid] = {
            "id": qid,
            "legacyId": legacy_id,
            "name": name,
            "category": category,
            "description": description,
            "sellPrice": obj.get("Price", 0),
            "edible": is_edible,
            # Edibility IS the energy value; health = int(edibility * 0.45)
            "energy": edibility if is_edible else 0,
            "health": int(edibility * 0.45) if is_edible else 0,
        }
    return out


# --- Recipes ------------------------------------------------------------------

def _parse_ingredients(s: str) -> list:
    parts = s.split()
    return [
        {"item": qualify(parts[i]), "count": int(parts[i + 1])}
        for i in range(0, len(parts) - 1, 2)
    ]


def _parse_source(raw: str) -> str:
    s = raw.strip()
    if not s or s.lower() == "null":
        return ""
    parts = s.split()
    if parts[0] == "s" and len(parts) >= 3:        # "s SkillName Level" -> skill unlock
        return f"{parts[1]} level {parts[2]}"
    if parts[0] == "l" and len(parts) >= 2:        # "l N" -> combat/other level
        return f"Level {parts[1]}"
    return s


def _parse_crafting(name: str, value: str) -> dict:
    p = value.split("/")
    # Field p[2] is either a type keyword ("BigCraftable"/"Object") or the result slot.
    is_bc = len(p) > 2 and p[2].lower() == "bigcraftable"
    has_type = len(p) > 2 and p[2].lower() in ("bigcraftable", "object")
    ri = 3 if has_type else 2          # result slot index
    result_slot = p[ri] if len(p) > ri else ""
    # Result slot may be "id" or "id count" (space-separated within the same slash-field)
    result_parts = result_slot.split()
    result_id = result_parts[0] if result_parts else ""
    result_count = int(result_parts[1]) if len(result_parts) > 1 else 1
    source_raw = p[ri + 2] if len(p) > ri + 2 else ""
    src = _parse_source(source_raw)
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "yields": qualify(result_id, bc=is_bc),
        "yieldCount": result_count,
        "ingredients": _parse_ingredients(p[0]),
        "source": f"Crafting — {src}" if src else "Crafting",
    }


def _parse_cooking(name: str, value: str) -> dict:
    # Cooking: "ingredients/unused_or_cond/result_id/count[/source]"
    p = value.split("/")
    result_id = p[2] if len(p) > 2 else ""
    result_count = int(p[3]) if len(p) > 3 and p[3].isdigit() else 1
    src = _parse_source(p[4]) if len(p) > 4 else ""
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "yields": qualify(result_id),
        "yieldCount": result_count,
        "ingredients": _parse_ingredients(p[0]),
        "source": f"Cooking — {src}" if src else "Cooking",
    }


def transform_recipes(crafting_raw: dict, cooking_raw: dict) -> list:
    out = []
    for name, value in crafting_raw.items():
        try:
            out.append(_parse_crafting(name, value))
        except Exception as exc:
            print(f"  [skip crafting] {name!r}: {exc}", file=sys.stderr)
    for name, value in cooking_raw.items():
        try:
            out.append(_parse_cooking(name, value))
        except Exception as exc:
            print(f"  [skip cooking] {name!r}: {exc}", file=sys.stderr)
    return out


# --- Bundles ------------------------------------------------------------------

# Map SV area key prefixes to display room names.
# Key format is "{area_name}/{bundle_id}" — area_name varies (human-readable or numeric).
_ROOM_MAP = {
    "spring foraging": "Crafts Room",
    "summer foraging": "Crafts Room",
    "fall foraging":   "Crafts Room",
    "winter foraging": "Crafts Room",
    "construction":    "Crafts Room",
    "exotic foraging": "Crafts Room",
    "spring crops":    "Pantry",
    "summer crops":    "Pantry",
    "fall crops":      "Pantry",
    "quality crops":   "Pantry",
    "animal":          "Pantry",
    "artisan":         "Pantry",
    "river fish":      "Fish Tank",
    "lake fish":       "Fish Tank",
    "ocean fish":      "Fish Tank",
    "night fishing":   "Fish Tank",
    "specialty fish":  "Fish Tank",
    "crab pot":        "Fish Tank",
    "blacksmith":      "Boiler Room",
    "geologist":       "Boiler Room",
    "adventurer":      "Boiler Room",
    "chef":            "Bulletin Board",
    "dye":             "Bulletin Board",
    "field research":  "Bulletin Board",
    "fodder":          "Bulletin Board",
    "enchanter":       "Bulletin Board",
    "missing":         "Vault",
    "vault":           "Vault",
    # Numeric area ids (fallback)
    "0": "Crafts Room", "1": "Pantry", "2": "Fish Tank",
    "3": "Boiler Room", "4": "Vault", "5": "Bulletin Board",
}


def _area_to_room(area_key: str) -> str:
    return _ROOM_MAP.get(area_key.lower().strip(), area_key)


def _parse_reward(reward_str: str) -> dict:
    """Parse reward string "O item_id count" or "BO item_id count" (letter or digit type prefix)."""
    parts = reward_str.strip().split()
    if not parts:
        return {"item": "(O)0", "count": 1}
    if len(parts) == 3 and parts[0] in ("O", "BO", "0", "1"):
        is_bc = parts[0] in ("BO", "1")
        return {"item": qualify(parts[1], bc=is_bc), "count": int(parts[2])}
    if len(parts) == 2:
        return {"item": qualify(parts[0]), "count": int(parts[1])}
    return {"item": qualify(parts[0]), "count": 1}


def _parse_bundle(area_key: str, bundle_id: str, value):
    bundle_name = f"{area_key}/{bundle_id}"
    room = _area_to_room(area_key)

    # SV 1.6: value may be a BundleData object
    if isinstance(value, dict):
        name = value.get("Name", bundle_name)
        slots = value.get("NumberOfSlots", 0)
        reward_raw = value.get("Reward", "")
        reward = _parse_reward(reward_raw) if reward_raw else {"item": "(O)0", "count": 1}
        raw_ingredients = value.get("Ingredients", [])
        items = [
            {
                "item": qualify(ing.get("ItemId", ing.get("itemId", "0"))),
                "count": ing.get("Stack", ing.get("stack", 1)),
                "quality": ing.get("Quality", ing.get("quality", 0)),
            }
            for ing in raw_ingredients
        ]
        return {
            "id": bundle_id.lower().replace(" ", "_"),
            "room": room,
            "name": name,
            "slotsRequired": slots or len(items),
            "reward": reward,
            "items": items,
        }

    # Legacy / pre-1.6: value is a slash-delimited string
    # "name/reward/items_string/color_index[/...]"
    if isinstance(value, str):
        p = value.split("/")
        if len(p) < 3:
            return None
        name = p[0]
        reward = _parse_reward(p[1]) if p[1] else {"item": "(O)0", "count": 1}
        item_parts = p[2].split()
        items = []
        for i in range(0, len(item_parts) - 2, 3):
            items.append({
                "item": qualify(item_parts[i]),
                "count": int(item_parts[i + 1]),
                "quality": int(item_parts[i + 2]),
            })
        return {
            "id": f"{area_key}_{bundle_id}".lower().replace(" ", "_"),
            "room": room,
            "name": name,
            "slotsRequired": len(items),
            "reward": reward,
            "items": items,
        }

    return None


def transform_bundles(raw: dict) -> list:
    out = []
    for key, value in raw.items():
        # Key format: "{area_name}/{bundle_id}" or just "{bundle_id}"
        if "/" in key:
            area_key, bundle_id = key.rsplit("/", 1)
        else:
            area_key, bundle_id = "unknown", key
        bundle = _parse_bundle(area_key, bundle_id, value)
        if bundle:
            out.append(bundle)
        else:
            print(f"  [skip bundle] {key!r}: unrecognized format", file=sys.stderr)
    return out


# --- Gifts --------------------------------------------------------------------

def _build_category_map(objects_raw: dict) -> dict:
    """Return category_int -> [qualified_item_id, ...] for all non-negative category items."""
    cat_map: dict[int, list] = defaultdict(list)
    for item_id, obj in objects_raw.items():
        cat = obj.get("Category")
        if isinstance(cat, int) and cat < 0 and cat != -999:  # -999 = Litter (map nodes, not items)
            cat_map[cat].append(qualify(item_id))
    return dict(cat_map)


def transform_gifts(raw: dict, objects_raw: dict) -> dict:
    """Invert NPC-centric NPCGiftTastes into item-centric gift reactions.

    Negative item IDs in the gift data are category codes (e.g. -6 = Milk).
    These are expanded to all items belonging to that category so each real
    item gets the correct NPC preference merged in.
    """
    # Slot indices in slash-delimited value:
    #   0=love_text  1=love_ids  2=like_text  3=like_ids
    #   4=dislike_text  5=dislike_ids  6=hate_text  7=hate_ids  8=neutral_ids
    SLOTS = {1: "loves", 3: "likes", 5: "dislikes", 7: "hates", 8: "neutrals"}
    cat_map = _build_category_map(objects_raw)
    gifts = defaultdict(  # type: ignore[var-annotated]
        lambda: {"loves": [], "likes": [], "neutrals": [], "dislikes": [], "hates": []}
    )

    # Maps (qid, npc) -> most-positive individual reaction seen in pass 1.
    # Used in dedup: individual beats category; among two individual reactions,
    # SV checks loves→hates in order so most-positive wins.
    PRECEDENCE = ["loves", "likes", "neutrals", "dislikes", "hates"]
    individual_reactions: dict = {}

    def _add_individual(qid: str, reaction: str, npc_name: str) -> None:
        key = (qid, npc_name)
        existing = individual_reactions.get(key)
        if existing is None or PRECEDENCE.index(reaction) < PRECEDENCE.index(existing):
            individual_reactions[key] = reaction
        if npc_name not in gifts[qid][reaction]:
            gifts[qid][reaction].append(npc_name)

    def _add_category(qid: str, reaction: str, npc_name: str) -> None:
        if (qid, npc_name) in individual_reactions:
            return  # individual reaction takes precedence
        if npc_name not in gifts[qid][reaction]:
            gifts[qid][reaction].append(npc_name)

    # Pass 1: individual item reactions (positive item IDs only)
    for npc_name, value in raw.items():
        if npc_name == "Universal":
            continue
        parts = value.split("/")
        for slot_idx, reaction in SLOTS.items():
            if slot_idx >= len(parts):
                continue
            for raw_id in parts[slot_idx].split():
                raw_id = raw_id.strip()
                if not raw_id or raw_id == "-1":
                    continue
                try:
                    id_int = int(raw_id)
                except ValueError:
                    _add_individual(qualify(raw_id), reaction, npc_name)
                    continue
                if id_int >= 0:
                    _add_individual(qualify(raw_id), reaction, npc_name)

    # Pass 2: category expansions — only fill (item, npc) gaps not covered by pass 1
    for npc_name, value in raw.items():
        if npc_name == "Universal":
            continue
        parts = value.split("/")
        for slot_idx, reaction in SLOTS.items():
            if slot_idx >= len(parts):
                continue
            for raw_id in parts[slot_idx].split():
                raw_id = raw_id.strip()
                if not raw_id or raw_id == "-1":
                    continue
                try:
                    id_int = int(raw_id)
                except ValueError:
                    continue
                if id_int < 0:
                    for member_qid in cat_map.get(id_int, []):
                        _add_category(member_qid, reaction, npc_name)

    # Dedup: an NPC can appear in multiple buckets when the same category code appears
    # in two taste slots, or when an item appears in two individual taste slots.
    # Precedence rules:
    #   1. Individual reaction > category reaction (use individual_reactions dict)
    #   2. If both individual: most-positive wins (SV checks loves→hates in order)
    #   3. If both category: most-positive wins as tiebreaker
    result = {}
    for qid, entry in gifts.items():
        # Collect every (npc -> [reaction, ...]) that has conflicts
        npc_seen: dict = {}
        for reaction in PRECEDENCE:
            for npc in entry[reaction]:
                npc_seen.setdefault(npc, []).append(reaction)

        clean = {r: [] for r in PRECEDENCE}
        for npc, reactions in npc_seen.items():
            if len(reactions) == 1:
                clean[reactions[0]].append(npc)
            else:
                ind = individual_reactions.get((qid, npc))
                if ind is not None:
                    # Individual reaction wins regardless of positivity
                    clean[ind].append(npc)
                else:
                    # Both category-derived: take most positive (first in PRECEDENCE)
                    winner = next(r for r in PRECEDENCE if r in reactions)
                    clean[winner].append(npc)
        result[qid] = clean
    return result


# --- Output / sample ----------------------------------------------------------

def _sample(label: str, data, n: int) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(data, dict):
        items = list(data.items())[:n]
        for k, v in items:
            print(f"  {k}:")
            print(f"    {json.dumps(v, ensure_ascii=False)}")
        print(f"  ... ({len(data)} total)")
    elif isinstance(data, list):
        for v in data[:n]:
            print(f"  {json.dumps(v, ensure_ascii=False)}")
        print(f"  ... ({len(data)} total)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir",  default="data/raw",  help="Directory containing CP export JSONs")
    ap.add_argument("--out-dir",  default="data",      help="Output directory for schema files")
    ap.add_argument("--write",    action="store_true", help="Write output files (default: dry-run)")
    ap.add_argument("--sample",   type=int, default=5, help="Number of sample entries to print per file")
    args = ap.parse_args()

    raw_dir = pathlib.Path(args.raw_dir)
    out_dir = pathlib.Path(args.out_dir)

    print(f"Reading from: {raw_dir.resolve()}")

    objects      = _load(raw_dir, "Objects.json")
    crafting     = _load(raw_dir, "CraftingRecipes.json")
    cooking      = _load(raw_dir, "CookingRecipes.json")
    bundles_raw  = _load(raw_dir, "Bundles.json")
    gift_tastes  = _load(raw_dir, "NPCGiftTastes.json")
    strings      = _load_strings(raw_dir)

    if strings:
        print(f"  Loaded StringsObjects.json ({len(strings)} keys) — DisplayNames will be resolved.")
    else:
        print("  StringsObjects.json not found — using internal Name field (run: patch export Strings/Objects).")

    items   = transform_items(objects, strings)
    recipes = transform_recipes(crafting, cooking)
    bundles = transform_bundles(bundles_raw)
    gifts   = transform_gifts(gift_tastes, objects)

    _sample(f"items.json  (keyed by qualified id)", items, args.sample)
    _sample(f"recipes.json", recipes, args.sample)
    _sample(f"bundles.json", bundles, args.sample)
    _sample(f"gifts.json  (keyed by qualified id)", gifts, args.sample)

    if not args.write:
        print("\n[dry-run] Pass --write to overwrite data/*.json")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "items.json").write_text(
        json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "recipes.json").write_text(
        json.dumps(recipes, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "bundles.json").write_text(
        json.dumps(bundles, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "gifts.json").write_text(
        json.dumps(gifts, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[written] {out_dir}/{{items,recipes,bundles,gifts}}.json")
    print(f"  items: {len(items)}, recipes: {len(recipes)}, bundles: {len(bundles)}, gift entries: {len(gifts)}")


if __name__ == "__main__":
    main()
