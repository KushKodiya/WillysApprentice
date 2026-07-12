# Phase 2a Spec — Chatbot Backend (headless)

Scope: the full question-answering pipeline, driven by an HTTP endpoint you
hit with curl. NO in-game UI (that's Phase 2b). This phase proves the
"brain" — retrieval, live state, and answer generation — is correct before
any UI is built on top of it.

The test for 2a: run the game (so the mod's state server is live), curl a
question at the Python chatbot service, and read a correct answer in your
terminal. If "what do I still need for the community center?" comes back
right, 2a works.

---

## 0. Load-bearing principle — the chatbot is optional

**The three features (wiki overlay, chatbot, automated fishing) are
independent. The wiki overlay and automated fishing must NEVER depend on
the chatbot or on any model being available. A missing/unreachable model
degrades ONLY the chatbot — never the overlay or fishing.**

Concretely:
- The mod loads and runs fully with no model configured. The overlay (Phase
  1) and fishing (Phase 3) work normally regardless.
- If no model backend is reachable, the chatbot reports itself
  "unavailable" (clear message) and everything else keeps working. No
  cascading failure, no startup dependency on a model.
- A config toggle lets a user disable the chatbot entirely, so the mod
  never tries to reach a model or build the embedding index.
- The mod **state server** (§2) is a pure read layer with NO model
  dependency. Both the chatbot (Phase 2) and fishing (Phase 3) consume it
  independently. It must never call a model or the chatbot service.

This principle is why a user who can't (or won't) run a model still gets the
full wiki overlay and automated fishing. Keep it inviolate across all
phases.

---

## 1. The direction flip — two local servers

Phase 1 had one server (Python serving wiki data; mod was the client).
Phase 2a adds a second: the mod must now expose live game state, so the
**mod becomes a server too**. Final picture:

- **Python wiki server** (from Phase 1, unchanged): serves static item data.
- **Mod state server** (NEW): a small HTTP server inside the mod exposing
  live game state read endpoints.
- **Python chatbot service** (NEW): receives a question, retrieves the
  relevant static data + live state (calling the mod's state server),
  assembles a focused context, calls the model, returns the answer.

Data flow for one question:
```
curl → chatbot service → [wiki data lookups]        (local, in-process)
                       → [mod state server]          (HTTP, live state)
                       → [model provider]            (Ollama or API)
                       → answer text → curl
```

> ponytail: mod state server + chatbot service are the two new pieces.
> Phase 2b will put a UI in front of the chatbot service — nothing in 2a's
> pipeline changes when that happens.

---

## 2. Mod state server (C#, NEW)

A small HTTP server inside the mod, bound to `127.0.0.1` on a fixed port
(default `5311`, separate from the wiki server's `5310`), exposing
read-only live game state. Loopback only, no auth (same rationale as
Phase 1).

### Endpoints (all GET, all return JSON)

**`GET /state/inventory`** — the player's current inventory.
```json
{ "items": [ {"id": "(O)128", "count": 3, "quality": 0}, ... ] }
```

**`GET /state/bundles`** — community center bundle progress.
```json
{
  "complete": false,
  "bundles": [
    {
      "id": "ocean_fish", "room": "Fish Tank", "name": "Ocean Fish Bundle",
      "complete": false,
      "slotsFilled": 2, "slotsRequired": 4,
      "missing": [ {"item": "(O)130", "count": 1}, {"item": "(O)701", "count": 1} ]
    }
  ]
}
```
`missing` is the key field — it's what makes "what do I still need" answerable.

**`GET /state/world`** — season, weather, day, time, player location.
```json
{ "season": "spring", "day": 12, "weather": "rain", "time": 1430,
  "location": "Farm" }
```

**`GET /state/player`** — skill levels and basic player facts.
```json
{ "fishingLevel": 4, "farmingLevel": 6, "miningLevel": 3,
  "foragingLevel": 2, "combatLevel": 5, "money": 12500 }
```

**`GET /health`** → `{"status":"ok"}`. Chatbot service pings on startup.

### Notes
- All endpoints read live game state via SMAPI APIs on the main thread —
  the HTTP server must marshal reads onto the game thread (same threading
  discipline as Phase 1's overlay; do NOT read game state from the HTTP
  handler's thread directly).
- If no save is loaded, endpoints return a clear "no save loaded" state
  rather than erroring, so the chatbot can respond gracefully.

**NOT in 2a:** any command/write endpoints (move, cast, etc.) — those are
Phase 3. This server is read-only.

---

## 3. Chatbot service (Python, NEW)

A new Python service (own port, default `5312`) exposing one endpoint:

**`POST /ask`**
```json
Request:  { "question": "what do I still need for the community center?" }
Response: { "answer": "You still need a Sardine and a Red Snapper for the
            Ocean Fish Bundle, and ...", "usedData": [...optional debug...] }
```

**`GET /health`** → reports whether the chatbot is actually usable:
```json
{ "status": "ok", "modelReachable": true, "provider": "ollama",
  "model": "qwen3:14b" }
```
If the model backend is unreachable, `modelReachable` is `false` and `/ask`
returns a clear, non-crashing message ("Chatbot unavailable — no model
backend reachable. Check your model config.") rather than erroring. This is
what lets the rest of the mod keep working when no model is available
(see §0).

If the chatbot is disabled via config, the service either doesn't start or
reports `"status": "disabled"` — and the mod treats that as "chatbot feature
off," with overlay and fishing entirely unaffected.

Internally, answering a question is a fixed-logic pipeline (NOT model-driven
tool-calling — see §5 for why):

1. **Parse** the question for intent + entities (which items/NPCs mentioned,
   is this about bundles / crafting / gifts / inventory / general).
2. **Resolve entities** — fuzzy item/NPC mentions → concrete ids via vector
   search (§4).
3. **Retrieve** — exact lookups into the Phase 1 wiki data for resolved
   ids; live fetch from the mod state server (§2) for anything about
   inventory / bundle progress / world / player.
4. **Assemble context** — build a small, focused text context from only the
   retrieved data. Hard budget: keep total prompt ≤ 4096 tokens (small
   local models degrade past this and 8GB RAM is tight). Because retrieval
   pre-filters, this is easy to stay under.
5. **Generate** — hand the context + question to the model provider (§6),
   which writes the natural-language answer.
6. **Return** the answer.

---

## 4. Entity resolution via vector search

The one place semantic search genuinely beats exact lookup: turning a fuzzy
mention ("the spicy root", "that mermaid fish", "the blue jazz flower") into
a concrete item/NPC id.

- Build an embedding index over item names (+ maybe categories/short
  descriptions) and NPC names, once, at startup or as a prebuilt artifact.
- Use a small local embedding model (e.g. via Ollama's embedding endpoint or
  a lightweight sentence-transformer) — embeddings are cheap and don't need
  the big generation model.
- At query time: embed the mention, nearest-neighbor lookup, return the best
  matching id(s) above a confidence threshold. Exact-name matches should
  short-circuit vector search (if the user typed "Pufferfish" exactly, just
  look it up).

> ponytail: exact match first, vector search only for fuzzy mentions.
> Vector search resolves the ID; all actual data retrieval after that is
> exact structured lookups into the clean Phase 1 data.

---

## 5. Why fixed-logic, not model-driven tool-calling

The retrieval is orchestrated by Python code, not by the model deciding
which tools to call. Rationale:

- Target hardware is an 8GB Mac running a 3–4B local model *alongside
  Stardew*. Small local models are unreliable at tool-calling (malformed
  args, skipped/hallucinated calls). Building correctness on that is risky.
- Fixed logic plays to the small model's actual strength: writing a fluent
  answer from data it's been handed, not orchestrating retrieval.
- The retrieval functions (get_item, get_bundle_status, get_inventory,
  check_gift, etc.) are built as clean, reusable Python regardless. So
  model-driven tool-calling remains a clean **future upgrade** — once the
  fixed-logic version works and a user has capable enough hardware/model,
  the same functions can be exposed as tools. Not in 2a.

---

## 6. Model provider — swappable interface

The single most important design point for portability. The answer-
generation call sits behind a small interface:

```
generate(context: str, question: str) -> str
```

with pluggable implementations:
- **OllamaProvider** (default) — calls a local Ollama model.
- **ClaudeProvider** — calls the Anthropic API (needs an API key).
- (future) any other provider — one more implementation.

Which provider + which model is read from a **config file**, not hardcoded:
```json
{
  "provider": "ollama",
  "model": "qwen3:14b",
  "ollamaUrl": "http://192.168.1.50:11434",
  "apiKey": null,
  "chatbotEnabled": true
}
```

### Ollama does not have to run on the same machine

The chatbot service reaches the model over HTTP, so the model can run
anywhere reachable — including a **separate home server** on the same
network. This is the recommended setup for this project, since it sidesteps
the 8GB RAM limit on the dev Mac entirely:

```
Mac (Stardew + mod + Python chatbot service + wiki data + mod state server)
   │
   └─ model generation ──LAN──→ home server running Ollama (lots of RAM)
```

The Mac only runs the game + lightweight glue; the memory-hungry model runs
on the server. To make this work:
- On the **server**: set `OLLAMA_HOST=0.0.0.0` so Ollama accepts LAN
  connections (it binds to 127.0.0.1 by default and would otherwise only
  accept same-machine requests).
- In the chatbot **config**: set `ollamaUrl` to the server's LAN address
  (e.g. `http://192.168.1.50:11434`).
- Keep this **LAN-only**. Do NOT expose the Ollama port to the public
  internet — it has no auth. For remote access use a VPN/Tailscale tunnel,
  not a public port.

Because the server has plenty of RAM, it can run a much larger model (14B /
32B) than the Mac could — a real quality jump over the 8GB-constrained
option, still free and fully local to the network.

### Default / per-user model selection

There is no single fixed model — each user picks what fits *their* setup via
config. The mod scales to whoever runs it:
- **This project's setup**: `ollamaUrl` → home server, a 14B–32B model
  (tune to the server's RAM).
- **User on a strong local machine**: local Ollama, larger model.
- **User on a modest laptop (e.g. 8GB Mac)**: local Ollama, a 3–4B model
  (`qwen3:4b` or `phi4-mini`) — works, more modest answers.
- **User with their own home server**: same as this project's setup, their
  address.
- **User wanting zero local model**: `provider: "claude"` + their own API
  key — best quality, minimal local RAM, small per-question cost.
- **User who can't/won't run any model**: set `chatbotEnabled: false`. The
  chatbot is off; the wiki overlay and automated fishing still work fully
  (see §0). This is a first-class supported configuration, not a
  degraded one.

Because model selection is per-user config, a shared/public release would
document these options as a "choose your model backend" setup step — the mod
ships the same for everyone, and the config differs.

---

## 7. Milestones / checkpoints (de-risking order)

Do these in order; each is a go/no-go before more is built on top.

1. **The Mac can reach the model on the home server over the LAN.** On the
   server: install Ollama, set `OLLAMA_HOST=0.0.0.0`, pull the chosen model
   (e.g. `qwen3:14b`, tuned to the server's RAM). From the Mac: confirm
   `curl http://<server-ip>:11434/api/tags` responds, and a test generation
   returns in reasonable time. This replaces the old "can an 8GB Mac run a
   model while gaming" check — the model runs on the server, so the Mac is
   unconstrained. VERIFY THIS FIRST — it validates the whole premise.
   (If the server is unavailable for a session, the fallback is a small
   local model on the Mac, or the Claude provider — same swappable
   interface.)
2. **Mod state server returns correct live data.** Curl each /state endpoint
   with a save loaded; confirm inventory, bundle `missing`, world, and
   player values match what's actually in-game.
3. **Entity resolution accuracy.** Test the vector resolver on a handful of
   fuzzy mentions; confirm it maps them to correct ids.
4. **End-to-end answer quality.** Curl representative questions at /ask and
   read the answers. Judge correctness by hand. Suggested test questions:
   - "What do I still need for the community center?"
   - "How do I craft a keg, and do I have the ingredients?"
   - "Who loves pufferfish?"
   - "What season is it and what's the weather?"
   - "What's this item worth?" (with an item mentioned)
5. **Graceful degradation.** Stop the model backend (or set
   `chatbotEnabled: false`) and confirm: the mod still loads, the wiki
   overlay still works, and `/ask` returns the "chatbot unavailable"
   message instead of crashing anything. This proves the §0 independence
   principle holds.

---

## 8. Config / open decisions to confirm

- Ports `5311` (mod state) and `5312` (chatbot) — placeholders, change if
  they clash.
- Model on the home server — pick a size to match the server's RAM (rough
  tiers: 32GB → ~14B comfortably, 64GB → ~32B). Confirm after checkpoint 1.
- Server LAN address for `ollamaUrl` — fill in the server's actual IP.
- Embedding model for entity resolution — pick a small one; can run on the
  Mac (it's cheap) or the server. Confirm whether to use Ollama's embedding
  endpoint or a standalone sentence-transformer.

## What's explicitly NOT in Phase 2a
- In-game chat UI (hotkey, input box, answer panel) — that's Phase 2b.
- Any command/write endpoints or automation — Phase 3.
- Model-driven tool-calling — future upgrade; 2a is fixed-logic.
- "Ways to get an item" data (fish locations, forage spawns, drops) beyond
  what current exports contain — needs more data assets; can be added to the
  retrieval layer later without changing the pipeline shape.
```