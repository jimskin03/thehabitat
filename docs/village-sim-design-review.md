# Design review: a simpler 2D agent simulation ("Village Sim")

Status: **proposal for discussion. No code has been written.**

This document proposes a new, smaller agent simulation that keeps the core idea of
thehabitat's `reverie` simulation (agents that live, remember and act on their own in a 2D
world) but with a much simpler design. It is a design review only. Nothing here changes the
existing `reverie` backend or the Django frontend.

## 1. Simulation concept

- A small waterside fishing village at night. Boats are moored along the shore, with a few
  huts, a jetty, a garden plot and a path along the water.
- A handful of agents (start with 3 to 5) live in the village. Each has a name, a short
  persona, a home, a daily routine and a few relationships.
- Agents move around a 2D grid, do simple activities (fish, mend nets, tend the garden,
  talk, rest) and can talk to nearby agents.
- Time advances in discrete steps (for example one step is 10 game minutes).
- The point of the project is to watch believable, mostly self-directed behaviour emerge,
  not to simulate a detailed world.

Reference art: the reference image is a mobile-game-style night scene of a waterside
village with boats along the shore. See open question 1 about whether it can be used.

## 2. Architecture

The key rule is that **agent logic and rendering never import each other**. They talk only
through a small, serializable world state.

```
+--------------------+      world state (JSON)       +--------------------+
|  Simulation core   |  ---------------------------> |  Renderer / UI     |
|  (agents, world,   |                               |  (background image |
|   clock, memory)   |  <--------------------------- |   + sprites)       |
+--------------------+   optional user commands      +--------------------+
          |
          v
   LLM provider (pluggable, can be mocked)
```

Proposed layers:

1. **World layer.** Grid size, walkable/blocked tiles, named places (home, jetty, garden)
   and objects with a state. Loaded from one JSON file.
2. **Agent layer.** Persona, position, current activity, a short memory list and a plan
   for the day. Pure Python with no web or drawing code.
3. **Decision layer.** One function, roughly `decide(agent, observation) -> action`. It
   can be rule-based, LLM-based or a mix. It must be replaceable and mockable so the
   simulation runs and is testable with no API key.
4. **Clock and runner.** Advances one step at a time, applies actions, and writes a state
   snapshot per step.
5. **Renderer.** Reads snapshots only. It can be a web page or a desktop viewer and it
   can even replay a recorded run.

Data contract between core and renderer (sketch, to be finalised):

```json
{
  "step": 42,
  "time": "21:20",
  "agents": [
    {"id": "mara", "x": 12, "y": 7, "activity": "mending nets", "speech": null}
  ],
  "events": ["mara greeted tom"]
}
```

Because the renderer only reads this file or stream, the core can run headless and fast,
and the renderer can be swapped without touching agent code.

## 3. Graphics approach

- **Background:** a static image of the village (or a lightly animated one: water shimmer,
  boat bobbing, lamp flicker via a few looping frames or simple shader-free tweens).
- **World to pixels:** an invisible tile grid laid over the background. Walkable tiles are
  hand-marked once (a JSON mask or a small tilemap editor export), so agents never need to
  understand the image itself.
- **Agents:** small sprites (or even coloured markers at first) moved between tiles, with
  an optional speech bubble and name label.
- **Cost:** no 3D, no physics, no per-frame heavy work. One background plus a few sprites
  is trivial for any browser or phone. Rendering is the cheap part.
- **Where the complexity lives:** agent logic, that is memory, planning, conversation and
  keeping behaviour believable over many steps. Budget design and testing time there, not
  on graphics.
- Upgrade path if wanted later: parallax layers, day/night tint, tile-based terrain
  instead of one flat image.

## 4. What to strip from the reverie design

Reverie is powerful but heavy. For the new project, propose to drop or simplify:

- **Full memory stream with embeddings and retrieval scoring.** Start with a short
  fixed-size list of recent events plus a few stored facts. Add retrieval only if needed.
- **Multi-level spatial memory and path-finding tied to a large Tiled map.** Use one small
  grid, a handful of named places, and plain A* or even straight-line moves.
- **Hierarchical daily planning with many LLM calls per step.** Use a day plan generated
  once (or a fixed schedule template) and call the model only when something interesting
  happens (meeting another agent, a conflict, a new event).
- **Reflection and relationship-update prompts.** Make these optional and run them rarely,
  for example once per game day.
- **Two cooperating servers sharing JSON files in several storage folders.** Use one
  process for the core and an optional separate viewer fed by a single snapshot file or
  stream.
- **Interactive stdin command loop and global config in a Python module.** Use a plain
  config file and a simple CLI with arguments.
- **Heavy per-step prompting costs.** Cap model calls per step and cache decisions.

Keep from reverie: the idea of persona plus memory plus plan, the discrete step clock,
JSON snapshots that can be replayed, and the practice of running with different model
providers.

## 5. Open questions

1. **Art rights.** The reference image appears to be a screenshot from a game. Can it be
   used in a public repo, or should we commission or generate an original village
   background in the same style?
2. **Platform.** Browser (canvas or Phaser-style) or a native viewer? Does it need to
   run on a phone?
3. **Reuse or standalone.** Should this live inside thehabitat (new folder) or in its own
   repository so it does not entangle with the reverie stack and its Docker setup?
4. **Model provider.** Which LLM provider and model, what per-step budget, and is a
   fully offline rule-based mode a hard requirement?
5. **Agent count and step size.** How many agents, and how long is one step in game time?
6. **Memory depth.** Is a short rolling memory enough, or do we want long-term recall
   across many game days from the start?
7. **Player role.** Pure observer, or can the user talk to agents and drop events in
   (a storm, a festival)?
8. **Persistence and replay.** Is saving runs and replaying them in the viewer a v1
   feature?
9. **Language and stack.** Python core as in reverie, or another language?
10. **Success criteria.** What does a good first demo look like (for example five agents
    running a full game day without human input)?

## Suggested next step

Decide questions 1 to 4, then write a one-page technical spec for the world file and the
snapshot format. Only after that start implementation.
