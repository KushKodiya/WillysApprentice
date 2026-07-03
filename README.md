# Willys Apprentice

An in-game companion for Stardew Valley that combines a live item wiki, an
AI chatbot for game questions, and automated fishing — all without leaving
the game.

## Overall goal

Playing Stardew Valley often means alt-tabbing to a wiki to check what an
item is used for, what a bundle still needs, or where to catch a specific
fish. This project brings that information (and more) into the game itself,
plus adds a conversational search tool and automation for one of the
game's more repetitive activities: fishing.

## Features

1. **Hover + hotkey wiki overlay** — hover any item (inventory, chest, shop,
   or the world) and press a hotkey to see what it's used to craft, which
   bundles need it, and who likes it as a gift.
2. **In-game AI chatbot** — ask natural-language questions ("what do I need
   for the community center?", "how do I catch a sturgeon?", "what's this
   fish worth?") without leaving the game. Combines wiki knowledge with your
   live save state.
3. **Automated fishing** — tell it what to fish for (or "fish until level
   N"), and it navigates to a valid location, checks season/weather/time,
   and fishes automatically until the goal is met.

## Architecture

The project is split across two processes that talk over a local API:

- **SMAPI mod (C#)** — the only code that touches the running game. It
  reads game state (hovered item, inventory, season/weather/time, player
  position) and executes commands (movement, casting). It contains no
  business logic — it's a thin bridge.
- **Python services** — everything else: the wiki data layer, the RAG
  chatbot, and the fishing decision logic. This is where almost all the
  "smart" behavior lives.

This split exists because Stardew Valley's live state is only accessible
through SMAPI's C# API — but there's no reason the reasoning and data logic
built on top of that state needs to be C# too.

```
SMAPI mod (C#)                          Python services
├─ Hover overlay                        ├─ Data layer (items, recipes,
├─ State + command bridge  <──local──>  │   bundles, gifts, fish info)
└─ Input simulator (fishing)    API     ├─ RAG chatbot (+ Claude API)
                                         └─ Fishing planner
```

## Phases

The project is built in three phases, in order, each shippable and playable
before the next begins.

### Phase 1 — Hover + hotkey wiki overlay

**Goal:** hover an item anywhere in-game, press a hotkey, see everything the
wiki would tell you about it.

- A small Python HTTP server (`127.0.0.1:5310`) loads a static wiki data
  dump (items, recipes, bundles, gift preferences) into memory and serves
  `GET /item/{id}`.
- The mod detects the hovered item — in menus (inventory, chests, shops) or
  in the world (placed objects, crops) — and on hotkey press (`Tab` by
  default) fetches and displays its data: crafting uses, bundle
  requirements, gift preferences.
- Responses are cached permanently per item per session, since the data is
  static.
- If the Python server is down, the mod shows "wiki offline" and the game
  is otherwise unaffected.

**Explicitly not in Phase 1:** NPC hover (deferred to Phase 1b), live game
state, the chatbot, fishing automation.

### Phase 2 — AI chatbot

**Goal:** ask the game questions in natural language and get answers that
combine static wiki knowledge with your actual save state.

- Adds live **read** endpoints to the state/command bridge (inventory,
  bundle progress, season, weather, time, player position) — this is where
  the mod becomes a server for the first time, since Python now needs to
  pull live state on demand.
- Builds a RAG layer in Python over the Phase 1 data layer, combined with
  live state, and calls the Claude API to answer questions such as:
  - "What do I still need for the community center?"
  - "What's needed to craft an iridium sprinkler, and do I have it?"
  - "Where do I catch a catfish?"

**Explicitly not in Phase 2:** command endpoints (movement/actions) or any
automation — this phase only reads state, it doesn't act on the game.

### Phase 3 — Automated fishing

**Goal:** name a target (a specific fish, or "fish until level N") and the
tool handles the rest.

- Adds **command** endpoints to the bridge (move-to, cast-rod) and an input
  simulator in the mod that executes the fishing minigame.
- The fishing planner (Python) checks the target's season/weather/time
  requirements against live state before acting, and notifies you if the
  target isn't currently catchable rather than fishing blindly.
- Supports open-ended goals ("keep fishing until I hit level 6"), not just
  single catches.

This is the highest-risk phase, since it's the only one that simulates
input and drives in-game actions — it's built last, once the bridge and
data layer have been proven out by Phases 1 and 2.

## Local API contract

The bridge between the mod and Python services evolves across phases:

| Phase | Server | Adds |
|---|---|---|
| 1 | Python | `GET /item/{id}`, `GET /health` |
| 2 | Mod | Read endpoints: inventory, bundle progress, season/weather/time, player position |
| 3 | Mod | Command endpoints: move-to, cast-rod |

Phase 1 uses plain HTTP request/response. Phases 2–3 introduce a
bidirectional WebSocket on the mod side once Python needs to subscribe to
live state or issue timed commands — deliberately deferred until that need
actually exists, rather than built speculatively.

## Data source

All wiki data (items, recipes, bundles, gift preferences, fish info) comes
from a static offline dump — never scraped live at runtime. The dump is
checked into the repo and regenerated offline when the game updates.

## Status

- [x] Architecture decided
- [x] Phase 1 spec approved
- [ ] Phase 1 implementation
- [ ] Phase 1b — NPC hover
- [ ] Phase 2 — AI chatbot
- [ ] Phase 3 — Automated fishing