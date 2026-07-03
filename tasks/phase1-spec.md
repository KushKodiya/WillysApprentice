# Phase 1 Spec — Hover + Hotkey Wiki Overlay

Scope: overlay only. No chatbot, no fishing. The only thing crossing the
mod↔Python boundary in this phase is **one item-data lookup** (mod asks,
Python answers).

---

## 1. Local API contract

### Direction & transport

Phase 1 has exactly one interaction: the mod, on hotkey, needs wiki data
for the item under the cursor. That is a stateless request→response keyed by
item id. So:

- **Transport: plain HTTP.** Mod is the **client**, Python is the **server**.
  The Phase 1 server is a small stdlib `http.server` or Flask app (~20 lines).
  Data layer stays in Python; loading JSON directly in the mod is a dead-end
  that gets torn out when Phase 2 arrives. *(Confirmed — not skipped.)*
- Bind `127.0.0.1` only, fixed default port `5310` (configurable in both mod
  config and Python config). Loopback-only, read-only static data → no auth.
- **WebSocket is deferred.** WS earns its place when Python needs to *subscribe*
  to live game state (Phase 2 chatbot) or push timed commands (Phase 3 fishing).
  None of that exists here. Adding it now is speculative. When those phases land,
  the **mod becomes the server** for state/command endpoints — likely a single
  bidirectional WS. Note the who-serves-whom flips by direction; that's fine,
  resolve it in Phase 2.

> ponytail: HTTP request/response, no WS, no auth. Add WS + the mod-as-server
> state/command API in Phase 2/3 when live subscription actually exists.

### Endpoints (Python server)

**`GET /item/{qualifiedId}`** — the only endpoint the overlay uses.
`qualifiedId` is the SV 1.6 qualified id, e.g. `(O)128`. URL-encode the parens.

Response `200`:
```json
{
  "id": "(O)128",
  "name": "Pufferfish",
  "category": "Fish",
  "description": "Inflates when threatened. Poisonous.",
  "sellPrice": 200,
  "edible": true,
  "energy": -50,
  "health": -22,
  "craftingUses": [
    { "recipeId": "maki_roll", "name": "Maki Roll", "yields": "(O)228" }
  ],
  "bundles": [
    { "bundleId": "ocean_fish", "room": "Fish Tank", "name": "Ocean Fish Bundle" }
  ],
  "gifts": {
    "loves": ["Sebastian"],
    "likes": [],
    "dislikes": ["Abigail"],
    "hates": []
  }
}
```
`404` if the id is unknown (mod renders "no wiki data"). Empty arrays are
valid (item has no crafting uses / bundles / gift reactions).

**`GET /health`** → `{"status":"ok","itemCount":N,"version":"1.0"}`. Mod pings
once on load; if it fails, overlay shows "wiki offline" and stops calling.

That's the entire Phase 1 surface. The architecture's read endpoints
(inventory/season/weather/time/position/bundle-progress) and command endpoints
(move-to/cast-rod) are **not** part of Phase 1 — they belong to the mod-as-server
side built in Phase 2/3.

---

## 2. Data layer schema

Source: a **static wiki data dump** (checked in as JSON, regenerated offline —
never live-scraped at runtime). Dataset is tiny (~a few thousand items, hundreds
of recipes, ~30 NPCs, ~30 bundles) and read-only.

**Storage: load the JSON files into in-memory dicts at startup, build reverse
indexes once.** No SQL, no migrations, serve from RAM.

> ponytail: JSON→dicts in memory. SQLite (`sqlite3`, stdlib) is the upgrade path
> if the dump grows past memory or we want ad-hoc queries — not needed at this size.

### Source files (the dump)

**`items.json`** — map keyed by qualified id:
```json
"(O)128": {
  "id": "(O)128", "legacyId": 128, "name": "Pufferfish",
  "category": "Fish", "description": "...",
  "sellPrice": 200, "edible": true, "energy": -50, "health": -22
}
```
`legacyId` = pre-1.6 numeric id, kept for cross-referencing older wiki/save data.

**`recipes.json`** — array:
```json
{
  "id": "maki_roll", "name": "Maki Roll",
  "yields": "(O)228", "yieldCount": 1,
  "ingredients": [ {"item": "(O)128", "count": 1}, {"item": "(O)258", "count": 1} ],
  "source": "Cooking - The Queen of Sauce"
}
```

**`bundles.json`** — array:
```json
{
  "id": "ocean_fish", "room": "Fish Tank", "name": "Ocean Fish Bundle",
  "slotsRequired": 4,
  "reward": {"item": "(BC)15", "count": 1},
  "items": [ {"item": "(O)128", "count": 1, "quality": 0} ]
}
```

**`gifts.json`** — **item-centric**, keyed by item id, reactions already resolved:
```json
"(O)128": { "loves": ["Sebastian"], "likes": [], "neutrals": [], "dislikes": ["Abigail"], "hates": [] }
```
Item-centric because that's exactly what a wiki item page shows and what the
overlay needs — no need to re-implement SV's per-NPC taste-precedence algorithm
(individual > universal > category). If we ever generate the dump ourselves
instead of lifting it from the wiki, *that* precedence resolver is the ceiling.

### Reverse indexes (built in Python at load, ~20 lines)

- `usedIn[itemId] → [recipe, ...]` (invert `recipes.ingredients`)
- `neededInBundles[itemId] → [bundle, ...]` (invert `bundles.items`)
- `gifts` is already item-keyed → direct lookup

A `/item/{id}` response = one `items` lookup + these three index lookups, merged.

---

## 3. Hover + hotkey overlay (mod side, C#)

### Resolving the hovered item id

There are two hover contexts. The mod checks both on every `Display.RenderedWorld`
/ `Display.RenderedActiveMenu` tick and tracks whichever produces a non-null id.

**A. Menu items (inventory, chest, shop)**

Inspect `Game1.activeClickableMenu`. For inventory-bearing menus the hovered
`Item` is already exposed via the menu's hover tracking (`hoveredItem` field or
the slot under the cursor). Read `item.QualifiedItemId` (SV 1.6, e.g. `(O)128`).
Keep `item.ParentSheetIndex` as a fallback for edge cases.

**B. World objects and crops**

When no menu is open, read `Game1.currentCursorTile` each tick and probe the
current location:

```
tile = Game1.currentCursorTile  // Vector2, updated by SMAPI

// Placed objects, forage, and big craftables — all in location.objects.
// QualifiedItemId prefix distinguishes them: "(O)…" vs "(BC)…" if the
// rendering layer ever needs to tell them apart.
if location.objects.TryGetValue(tile, out var obj):
    id = obj.QualifiedItemId          // e.g. "(O)16", "(BC)15"

// Crops (via HoeDirt terrain feature)
elif location.terrainFeatures.TryGetValue(tile, out var tf) && tf is HoeDirt hd && hd.crop != null:
    id = ItemRegistry.QualifyItemId(hd.crop.indexOfHarvest.Value.ToString(),
                                    ItemRegistry.type_object)  // "(O){n}"
```

All three paths produce a qualified id; the rest of the pipeline is identical.

**Deferred — NPC hover:** when the cursor tile contains an NPC the display model
inverts (show NPC gift preferences, not item page). Needs a separate panel layout
and a second reverse index (`npcGifts[npcName] → {loves, likes, ...}`). Deferred
to Phase 1b — no API or data-layer changes required, just a second panel and
the reverse index.

### Hotkey → lookup → render

1. Configurable keybind (SMAPI keybind, default `Tab`). On press while any of
   the above contexts has a non-null id, use it.
2. Cache-first: if the mod already has this id cached, render instantly.
   Otherwise fire `GET /item/{id}` on a **background task** (never block the
   render thread) — render "loading…", then update on completion.
   **Cache is permanent** — the data is static, so each id is fetched at most
   once per session.
3. Render an overlay panel near the cursor via `Display.RenderedActiveMenu`
   (for menus) or `Display.RenderedWorld` (for world hover) + SpriteBatch:
   name, sell price, crafting uses, bundles, who loves/likes it.
4. Dismiss on hotkey toggle-off or cursor leaving the tile/slot.

### Degrade gracefully

If `/health` failed at load or a lookup errors/times out, the overlay shows
"wiki offline" and the game is otherwise unaffected. Python being down never
breaks the mod.

> ponytail: fetch-on-hotkey + permanent per-item cache. Optional later:
> prefetch every item in an open inventory on menu-open to warm the cache.
> Skip until a hover feels slow.

---

## Open decisions to confirm

- Port `5310` and default keybind `Tab` — placeholders, change if they clash.
- Where the dump comes from (which wiki export/tool) and its regeneration
  cadence — out of scope for this spec, but it's the input the schema assumes.

## What's explicitly NOT in Phase 1
- Game-state read endpoints, command endpoints, WebSocket, mod-as-server direction — Phase 2/3
- NPC hover (gift-preference panel, NPC reverse index) — Phase 1b
- Chatbot, fishing — Phase 2/3
