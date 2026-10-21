# redfront (working title)

Русская версия: [README.md](README.md)

A dynamic campaign generator for DCS World on the Cold War Germany map (Python + pydcs, Lua mission scripts, a
browser-based campaign window). Full cycle: campaign model → day plan → mission → flight in DCS → debrief → next day.

## Contents

1. [What it is](#what-it-is)
2. [Installation and launch](#installation-and-launch)
3. [Quick start: the day cycle](#quick-start-the-day-cycle)
4. [Interface](#interface)
5. [Campaign and model](#campaign-and-model)
6. [Air war](#air-war)
7. [Doctrines](#doctrines)
8. [Orders of battle and theatre](#orders-of-battle-and-theatre)
9. [Data and files](#data-and-files)
10. [Verified / not verified](#verified--not-verified)
11. [Tests](#tests)
12. [Credits and licences](#credits-and-licences)

---

## What it is

The player picks a side, and with it the AI behaviour and front logic. Which aircraft to fly is up to the player.

### Three layers

| Layer | Where | Contents |
|---|---|---|
| Campaign model | campaign `state` (`camp.json`), `model.py`, `sim.py`, `ops.py`, `logistics.py` | "maps and arrows": units with strength by type, state and route; places, airfields, depots, bridges; hourly ground model |
| Day plan | `planner.py`, `ato.py`, `command.py` | daily air tasking order (ATO) for both sides: tasks, packages, timing |
| DCS mission | `build.py`, `materialize.py`, `redfront/lua/*.lua` | `.miz` via pydcs: a detailed window around the player's sortie plus the rest of the theatre at lower density; mission scripts; debrief hook |

Data the model is built from:

| Data | Files | Contents |
|---|---|---|
| Side doctrine | `redfront/data/doctrine/<package>.json` | tasks, performers by role, flight profile, march order, thresholds, ground model coefficients. Packages: `wp` (Warsaw Pact), `nato` (NATO, blue default), `generic` (generic profile) |
| Order of battle | `redfront/data/oob_*.json` or your own file | any types pydcs knows (class name or DCS id), each unit has a role; side countries |
| Sector | `redfront/data/sector_*.json` or your own file | places, links, airfields, depots, bridges, fixed air defence sites |

Link tables: `roles.json` (roles and categories: air / heli / ground / sam), `aircraft.json` (aircraft type
properties) and `payloads.json` (task-based payloads from DCS Retribution).

Where planner numbers come from: air unit radius — `strike_radius_km` on the unit, otherwise on the role; SAM radius —
`threat_radius_km` on the unit, otherwise on the role, otherwise the largest launcher `threat_range` from pydcs (that is
the range against a high-altitude target; it is overstated against a low-flying one; see also radar horizon below).

Mod types (Su-24, MiG-31 etc.) unknown to pydcs are not supported; registering them is a separate step.

### Mission window and conservation rule

The mission contains a detailed window around the sortie:

1. **target area** — the target is deployed as a piece of its unit using a formation template;
2. **route corridor** — SAMs that can reach the route;
3. **rest of the theatre** — at lower density (see [Whole theatre in the mission](#whole-theatre-in-the-mission)).

**Conservation rule:** a deployed vehicle carries weight = serviceable vehicles of that type in the model / deployed
vehicles of that type. At any density (`--density`, mission budget) losses in DCS are returned to the model faithfully.

### Principles

* **Realism from sources.** Mechanics are based on open sources (citations in the text and in the `source` /
  `method_source` fields of the data).
* **Anything not from a source is an estimate.** Every such number is marked: in data — `"estimate": true`,
  `estimate_fields`, `*_note` fields; in code and text — ОЦЕНКА / "estimate". Unit compositions, rates, radii,
  payloads, altitudes, march orders and coefficients are estimates. Coordinates of towns, depots and bridges are
  approximate and should be checked in the DCS mission editor.

---

## Installation and launch

### Ready-made program (Windows, no Python or git)

Build — `.github/workflows/release.yml` (PyInstaller on Windows in GitHub Actions; before packaging, the built program
creates a campaign, plan and mission as a check). To get the archive:

* release: push a version tag — `git tag v0.10 && git push origin v0.10`; the archive `redfront-v0.10-windows.zip`
  appears in the repository Releases;
* without a release: GitHub → Actions → release → Run workflow; the archive is in the run artifacts.

The archive contains a `redfront` folder with `redfront.exe`, `README.md` and `ЗАПУСК.txt`: unpack and run
`redfront.exe` (the campaign window opens in a browser; campaigns are stored next to the program). The program is not
signed — Windows may warn about an "unknown publisher".

### From source (Windows)

Requires Python 3.11+ (tick "Add python.exe to PATH" during install) and Git (pydcs is installed from GitHub).
In PowerShell in the project folder:

    py -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    .venv\Scripts\python tools\smoke_test.py             # test without DCS

`.venv\Scripts\python` is called directly: activating `Activate.ps1` is not needed (many systems block it via the
script execution policy). Campaign window — `run.bat` (`python -m redfront gui`); the first `run.bat` run creates
`.venv` itself.

### DCS requirements

* Cold War Germany map.
* **The debrief hook needs `io`/`lfs` unlocked** in `<DCS>\Scripts\MissionScripting.lua`: comment out the lines
  `sanitizeModule('io')` and `sanitizeModule('lfs')` (keep a backup; DCS updates restore the file). The Saved Games
  folder may be named `DCS` or `DCS.openbeta` — the hook writes to `lfs.writedir()`.

---

## Quick start: the day cycle

In the window: **New** (campaign) → **1. Plan** → **2. Mission** → fly in DCS → **3. Debrief** → **4. End of day**.

* **Plan** builds the daily ATO for both sides.
* **Mission** builds the `.miz` for the chosen sortie into `Saved Games\DCS*\Missions`.
* After the flight, **Debrief** finds the hook file itself (`Saved Games\DCS*\redfront`) and applies losses, landings,
  movements and intel to the model. The campaign clock moves to the end of the mission; later sorties stay in the plan.
* **End of day** finishes the day and builds a new plan.

The same from the console:

    .venv\Scripts\python -m redfront new     camp.json [--side red|blue] [--oob my_oob.json] [--sector ...] [--doctrine blue=generic]
    .venv\Scripts\python -m redfront plan    camp.json
    .venv\Scripts\python -m redfront ato     camp.json [--side own|enemy|all]
    .venv\Scripts\python -m redfront build   camp.json day1.miz [--task N] [--fly strike|sead|recon] [--humans N] [--budget N] [--density 1.0] [--ai]
    # fly day1.miz in DCS
    .venv\Scripts\python -m redfront debrief camp.json [file]
    .venv\Scripts\python -m redfront end-day camp.json
    .venv\Scripts\python -m redfront status  camp.json

Other commands: `gui [--port 8765] [--no-browser]`, `menu [campaign.json]` (text menu: status, plan, build, debrief,
end of day, new campaign — by entering numbers; also `run.bat menu`), `roads-probe`, `roads-apply`, `map-probe`,
`map-apply`, `map-import`, `set-damage` (manually set damage 0..1 of a rear-area object if the debrief did not count
it), `set-pos` (correct rear-area object coordinates from the DCS editor).

`new` options: `--name`, `--date` (default — preset date), `--seed` (repeat a campaign), `--variant NAME` (scenario
variant), `--no-random` (no randomness), `--roads <file>`.

---

## Interface

The campaign window is a browser page (`redfront.exe`, `run.bat` or `python -m redfront gui`).

### Window layout

* **Top bar** — campaign, "New", day cycle buttons, day and situation time; on the right — panel toggles
  (◧ left, ⬓ matrix, ◨ inspector), ⚙ settings, ? help.
* **Left** — list tabs (Sorties, Ground, Air units, Logistics, Log) and program messages.
* **Centre** — the map. For the selected sortie it shows each group's route in its own colour, waypoints with times
  (takeoff, rendezvous, IP, target, landing) and the SAM zones of the corridor; the legend can be collapsed.
* **Right — inspector** of the selection: a sortie (time on target, groups, each group's route with waypoint times,
  threats, "what a strike achieves", mission build, "Edit", "Remove") or a map object (unit, SAM, depot, bridge — click
  its symbol).
* **Bottom — synchronization matrix**: one row per sortie group, a bar from takeoff to landing, ○ rendezvous, ◆ on
  objective, dashed line — the sortie's time on target, shading — night, yellow line — campaign clock. The ⇔ handle of
  an own sortie can be dragged: the sortie moves in 5-minute steps, the server checks aircraft and timing (if it does
  not fit, the sortie stays unchanged and the reason is shown). Filters: duty stations, completed; zoom with −/+.
* Selection is shared: a sortie selected in the list, the matrix or on the map is highlighted everywhere. Panel widths
  and the matrix height are changed by dragging the borders and remembered in the browser.

### Header

* campaign selector;
* **New** — new campaign: theatre (sector), order of battle (preset or "(own)"), side. "Copy for editing" puts a
  copy of the selected preset into `presets/<name>.json` (edit in a text editor: units — `units`, type `type`, count
  `count`, airfield `base`, role `role`); it then appears in the list as "(own)";
* **⚙ Settings**, **?** (help);
* day cycle buttons: **1. Plan**, **2. Mission**, **3. Debrief**, **4. End of day**.

The window shows the situation time ("Day N, situation at HH:MM").

### Tabs

* **Sorties** — your side's sorties from the daily ATO, sorted by time on target (one card per sortie: "takeoff 09:01,
  on target 09:15"). The selected sortie opens in the inspector: package groups, threats in the corridor,
  "what a strike achieves"; there you choose the group you fly and the number of humans, and build the mission.
  **Commander mode** (`redfront/command.py`):
  * "Edit" — time on target; for each package group the performing unit (only with the group's role and within
    range of the objectives; route from its airfield), number of aircraft (1–4), payload ("by task" or any DCS
    Retribution payload for that type);
  * "Remove" — any own sortie, including standing orbits and airlift;
  * "+ sortie" — tasks the planner found but did not schedule (plan limits): place at their own time or the first
    free slot.

  Every change is checked against the side's whole plan as during plan generation (enough aircraft for the whole
  sortie plus turnaround; only night-capable types fly at night). If an edit does not fit, the sortie stays as it was
  and the window shows the reason. Sorties the player does not fly are resolved by the model with the new
  composition and time. The enemy plan cannot be edited.
* **Ground** — ground units: own; enemy — per intel.
* **Air units** — air units: crews, "Pilots, livery", "Add regiment" (from the historical list or custom), "Rebase".
* **Logistics** — supply: depot stocks (%, t, "cut off"), supply routes, the "Logistics (previous day)" summary (inflow, by air,
  consumption, "convoys destroyed — undelivered"), "What tonnes mean" (consumption, inflow, days of stock, industry).
  Enemy depot stocks are an estimate only, without tonnes.
* **Log** — event log.

### Map

Tactical map of the sector (`redfront/web/tactical.js`, unit classification — `redfront/symbols.py`):

* Base layer — paper (OSM, muted), topographic (OpenTopoMap) or none; the choice is remembered.
* **Front line** — boundary between the sides' territories: each map point belongs to the side whose place or field
  unit is closer (Voronoi diagram on a grid). Along both sides of the boundary — the forward edge: red line for red,
  blue for blue; territories are lightly tinted. A unit behind enemy lines (air assault, breakthrough) gets its own
  "island".
* **Symbols follow the player's side.** Playing red — the rules of the Soviet Army commander's working map (I.D.
  Pombrik, N.A. Shevchenko, "Рабочая карта командира", 1967; БУ СВ part II, 1983): own motor rifles, tanks, air assault
  and aviation in red, own air defence and all own labels in black, the enemy in blue, own routes in brown; labels
  horizontal, italic. Equipment symbols: tank — rhombus, IFV — "bullet" with a bar at the rear, APC — "bullet",
  transport helicopter — with air assault troops; own symbols face the enemy, air defence faces the top edge.
  Defence — closed outline with ticks along the forward edge; reserve and assembly — "area occupied by a unit" (dashed
  — planned); march — column on vehicles (echelon ticks: battalion — three, company — two); attack — broken arrow;
  combat-ineffective unit — "halted on line", withdrawal — withdrawal symbol; air assault — landing area with a
  helicopter symbol. SAM — missile launcher in a circle (ticks — range), GCI — search radar; depot — square "ГБ" (fill
  — stock, dashed — cut off); bridge and destroyed bridge — topographic symbols. Labels — field manual abbreviations
  ("94 гв. мсд", "1 тбр 1 тд США", "2/271 пдб"), ⚠ — not fully supplied. Playing blue — NATO APP-6: own — light-blue
  rectangles, enemy — red diamonds, branch symbol in the frame, echelon (II, X, XX) above the frame.
* Airfield — aircraft silhouette: active — filled, closed or lost — outlined and crossed out; colour — owner. FARP — a
  circle with "T": occupied — filled, free — outlined.
* Enemy SAM engagement zones — dashed with fill, own — faint; data older than 2 days — pale ("outdated"). Unit route —
  the near leg. Own supply routes — layer "Supply routes" (width — flow). Own downed crews are shown on the map.
* At small scales labels, SAMs and FARPs are hidden; place links (road graph) are a separate layer, off by default.

### Settings (⚙)

* language: Русский / English;
* mission ground vehicle budget (see [Mission budget](#mission-budget));
* show the enemy air plan (debug);
* DCS map tools: "Map probe", "Apply probe", "Roads probe", "Apply roads", import `.miz` with zones (see
  [Roads](#roads) and [Map objects](#rear-area-objects-on-the-dcs-map)).

---

## Campaign and model

### Operational level

The sector is a graph of places (`places`, `links`) with owners; the front line is the set of links between places of
different sides. Each side's command (`ops.py`) gives orders to its units according to the posture in its doctrine
package:

* `offense` (red) — free strong units attack neighbouring enemy places closest to the operation objective
  (`objectives` of the sector; in the whole-map theatre — 8 axes, `objectives.red`, unit field `axis`);
* `defense` (blue) — occupy unoccupied front places; spare strong units retake empty places.

Weakened units break contact, withdraw to the rear and recover; a place is held if a unit of that side is near and no
enemy is. Reserves arrive on their day (`arrives_day`). Coefficients are estimates (`sim` section of the doctrine,
`ops_note`). `status` shows places of both sides and the front line.

**Randomness.** On `new` a scenario variant (`variants` in the OOB) and reserve arrival spread are chosen; in combat
— loss spread, in offense — weighted choice of direction. Everything is repeatable with `--seed`; `--variant NAME` —
explicit variant; `--no-random` — no randomness. Coefficients are estimates (`random_note`).

### Doctrinal operational techniques

Parameters live in the doctrine `sim` section (estimates based on Ionin "Tactics" 1987, Savkin 1972, Donnelly
"Red Banner" 1988; FM 100-5 1982/1986, FM 71-100 1990, RAND R-3385). Decisions are taken every 6 h together with the
side commanders (`ops.py`).

* **Artillery in combat** (both sides): unit power ×(1 + `artillery_factor` (0.25) × share of serviceable guns in its
  supporting battery). Guns destroyed in a mission weaken the unit in the model too.
* **Prepared defence** (both sides): a unit defending without contact digs in; after `prepared_h` (12 h) its combat
  losses are ×`prepared_factor` (Warsaw Pact 0.75, NATO 0.65 — emphasis on prepared lines). A new route resets it.
* **Assault river crossing:** a destroyed major bridge closes supply but not manoeuvre — units cross with a delay
  (path longer by `crossing_km`: WP 30, NATO 40; march on that link ×`crossing_slow`).
* **WP — forward detachment:** the strongest free unit (strength 85%+) is sent to a line in depth (`forward_depth`
  places beyond the front on the way to the operation's objective) and moves faster than the main body (×1.5). One per side.
* **WP — second echelon committed in the sector of success:** arriving reserves enter not at their pre-assigned area
  but behind the own front place (within 100 km of it) where own forces are strongest relative to the enemy; a single
  sector is not flooded.
* **WP — operational manoeuvre group:** from day `omg_from_day` (2), after a breakthrough (an enemy front place with no
  enemy units within 15 km) a strong free unit drives into depth towards the nearest enemy depot or bridge (×1.3). A
  captured place with a depot means the depot is lost to the enemy (its supply stops).
* **NATO — covering force / delay:** a defending unit facing an enemy twice as strong, with strength below 80%, falls
  back to the next line instead of fighting to destruction.
* **NATO — counterattack by reserves:** a strong free unit strikes an enemy unit that has penetrated into own
  territory if it is 1.2 times stronger and within 60 km.
* **Tempo:** the daily log shows places taken and the furthest advance of the attacking side's units against the
  doctrine norm (`tempo_km`, WP ~40 km/day).

### Hourly ground model

Ground model (`sim.py`, coefficients in the doctrine `sim` section, estimates): units follow routes until contact
(`contact_km`); in contact they take losses according to the force ratio (equipment weighted by role; the defender
loses less) and leave combat below the combat-effectiveness threshold. A unit that reaches the end of its route
occupies an area (defence). Attached air defence takes losses together with its unit.

March rate: out of contact (enemy farther than `road_clear_km`, 15 km — the deployment line) a unit moves as a march
column at `road_march_km` per day (150 km, estimate); closer — at the attack rate (`daily_advance_km`, 25 km). A unit
may set its own `road_march_km` (0 — always the attack rate; used in the Hamburg training scenario). In the "Warsaw
Pact strike along the whole front" scenario (variant `assembly`) the WP first echelon starts in assembly areas at the
border and day-1 NATO brigades in border towns (forward defence); combat begins in the first hours of day 1
(`model.assembly_areas`). Unit positions on the road (`model.unit_pos`) use a cached route geometry: the end of day
for the whole front takes seconds rather than minutes.

The model follows the campaign clock (`sim.advance`): step — 1 h, combat and march per step — 1/24 of the daily norm
(strength recalculated every hour), place capture — every hour, command decisions — at 00, 06, 12 and 18 h (rear-area
recovery — 6 h). Supply, repair, replacements and the fate of downed crews — once a day, at its end.

* **The mission sees the world at its own time.** Building a sortie advances the model to mission start and moves the
  task target and group routes to the target's position at that time (`planner.refresh`). The model never goes back:
  sorties earlier than the situation time drop out of the plan.
* **Window of a flown mission.** Combat and marches in it happened in DCS (applied by the debrief), so the model
  passes that window with ATO events only, without combat or marching.
* **Night** — hours outside the flying day (06–20). At night march ×0.6, combat losses ×0.5 (`night_march`,
  `night_battle`). Estimates.

### Combat in the mission

A mission against troops in contact sets up the whole battle: both sides in combat formations within weapon range of
each other, air defence behind; losses in the mission go into the model.

* `lua/front.lua` (idea — the Troops in Contact script, Grendel, MIT; own code, no MOOSE): units stand in platoons of
  4 vehicles (vehicle names from the model). Platoons do not fire on their own: the script gives them short fire
  windows at a point 25–80 m from a random enemy vehicle within weapon range — a noisy battle with few losses (losses
  are computed by the model). The attacker moves to its firing line and, below 60% strength in the mission, falls back
  to its start position; defending platoons shift slowly. AI aircraft can see the targets. Numbers are estimates
  (`build.FRONT_CFG`).
* `lua/battle_site.lua` places the battle on the terrain at mission start (pydcs does not know the terrain): the
  whole battle shifts within 2.5 km to where there is less water, slope and buildings under the positions, then each
  vehicle moves to the best point nearby (road > roadside > field > built-up; water and slopes excluded). Platoons are
  respawned with the same names and groupId. The site is written to the debrief and remembered (`battle_sites`). Air
  defence positions are put in open ground (field, roadside, not on the road and not in buildings; at least 80 m
  apart; shift up to 400 m), no closer than 150 m to airfield concrete; a position on an airfield, in water or in a
  town (5 or more buildings within 150 m) is moved as a whole (up to 8 km). DCS does not expose forests to scripts.
  Weights are estimates (`build.SITE_CFG`).
* Only air defence (roles `sam_*`) fires at aircraft; other ground groups engage ground targets only
  (`OptRestrictTargets`, set in the .miz and again after a column is moved onto the road). A unit's organic air
  defence (`attached_to`) moves as a separate group in the column right behind the tanks.
* A SAM position faces the threat axis (`heading_deg` on the unit, otherwise the bearing to the nearest enemy
  airfield); otherwise the radar (e.g. Patriot) looks the wrong way.

### Battle formations and artillery

A unit in battle is laid out according to its side's doctrine (`redfront/formations.py`; estimates based on the
field manuals, distances compressed to the mission vehicle budget): vehicles are split into companies of 10 (tanks and
IFVs in each company).

* **Warsaw Pact** (Soviet Ground Forces Combat Regulations; Ionin, "Tactics", 1987): defence — company strongpoints,
  two thirds of the companies in the first echelon (1 km front per company), one third in the second (1.5 km behind);
  attack — companies in line (700 m front), tanks ahead, IFVs 150 m behind, one third of the companies in the second
  echelon.
* **NATO** (FM 71-1, FM 71-2, 1988): defence — company teams in staggered battle positions (1.4 km apart, 600 m
  stagger), vehicles in an arc; attack — the lead team in a wedge, the others staggered behind in overwatch.

**Artillery.** Each unit in battle gets a supporting battery (6 guns: 2S1 Gvozdika for the Warsaw Pact, M109 for
NATO; estimate) 6 km behind its line. In the mission it fires 4 fire missions on the enemy line (24 rounds each,
250 m dispersion). Lost guns are remembered by the unit (the battery is smaller in later missions) and are restored
at one per day. The ground model does not track artillery separately — its fire is part of combat attrition.

### Air defence network

`lua/iads.lua` (idea from Skynet IADS, own implementation; values are estimates):

* **Network nodes** — the side's GCI/early-warning radars (ground) and AWACS (A-50, E-3A).
* **Medium- and long-range SAMs that are connected** (a live ground node within 150 km or an AWACS airborne) keep their
  radars off until the network sees an enemy aircraft closer than their engagement range ×1.15; radars stay on for
  60 s after the last contact.
* **Without a connection** (nodes destroyed or too far) SAMs act autonomously: radars on all the time (DCS default AI),
  revealing themselves earlier.
* **An anti-radiation missile launched** towards a SAM (±20° cone, up to 120 km): with a probability by type (older
  SA-2, SA-3, SA-6, Hawk, Rapier — 0.3; Roland, SA-8, SA-19, Gepard, ZSU-23-4 — 0.5) the SAM notices it and shuts its
  radar down for the missile's flight time plus 120 s — this is suppression: the strike gets through, the SAM
  survives. Patriot (can shoot down ARMs) keeps radiating.
* **Campaign:** a destroyed GCI site stays destroyed in the model, and SAMs in its area work without the network in
  later missions. NATO ground radars (NADGE) are not in the order of battle — the blue network node is the E-3A only.

### Front on the F10 map

The mission (`redfront/frontline.py`, mission editor drawings) gets, on each side's layer, that side's picture at
mission start — the same calculation as in the program window: the line of contact (red and blue lines from the
sides' places and field units), own territory as a light fill, places as dots with names, and the side's operation
objectives highlighted ("◎"). The enemy is shown per own intelligence: units known only by presence do not move the
line. Line and fill are not drawn further than 45 km from places and units. The F10 map shows your coalition's layer.

### Roads

pydcs has no road network; only DCS knows roads (`land.findPathOnRoads`). If the model does not know the roads of the
legs a column follows, the mission moves the column onto the road in its first second (`lua/column_road.lua`: same
group, same vehicle names and groupId) and writes the paths found into the debrief file; after `debrief` the model
remembers them. If DCS finds no road, the column stays in place (a line in the debrief log).

Roads for the whole theatre at once — a utility mission: "Roads probe" in settings or
`roads-probe <out.miz> --sector sector_germany.json --oob oob_germany.json`, run it in DCS, then "Apply roads" (or
`roads-apply camp.json <roads_*.json>`, `new ... --roads <file>`). A new campaign picks up roads by itself: from Saved
Games (`redfront\roads_<sector>.json`), otherwise from the distribution (`redfront/data/roads_<sector>.json` if
present). A road longer than 2 × straight line + 15 km (DCS sometimes returns a huge detour) is rejected — the leg is
taken as a straight line. The place graph is measured along roads where known.

### Rear area: airfields, depots, bridges

* Military airfields only (list in the sector file, from memory of 1980s bases — to be checked). Enemy within 30 km
  — airfield closed, squadrons rebase to the nearest open own airfield; enemy on the airfield — lost (it does not pass
  to the enemy). Airfield damage — fewer aircraft available. Squadrons are replenished to establishment.
* Bridges on links: a destroyed bridge closes its links for 3 days.
* Targets in the mission are map objects in the target area (`lua/targets.lua`, like "Assign as" in the editor): the
  hook records their destruction, the debrief converts it into damage. Coefficients are estimates (`logistics_note`,
  `debrief.FULL_DAMAGE`).
* Airfield coalition in the mission follows the model: the sides' military airfields belong to their coalitions, lost
  and other airfields are neutral. DCS airfield warehouses are unlimited.

#### Rear-area objects on the DCS map

Depot and bridge coordinates are estimates and need to be tied to real map objects: "Map probe" (`map-probe`) — a
utility mission that finds bridge and depot objects of the sector; "Apply probe" (`map-apply` to a campaign or sector
file); import a `.miz` with "Assign as..." zones (`map-import`, ROLE = depot|bridge, VALUE = object id); `set-pos`.

### Supply in tonnes

One quantity — "supply", in tonnes (fuel and ammunition together). All numbers are estimates (`supply_t_note`, `sim`):

* **Depot** — stock `stock_t` out of capacity `cap_t` (the side's depot capacity — `depot_days` = 10 days of its
  defensive consumption, split evenly). Depot damage destroys stock above capacity × (1 − damage).
* **Consumption** per unit per day — serviceable vehicles (incl. attached air defence) × `consume_t` by state: combat
  1.0 t, march 0.5, recovery 0.3, defence 0.2 t per vehicle. A unit draws from own depots within `supply_km` over own
  territory; combat first. Receiving a share of the norm — strength between `supply_power_factor` and 1, march between
  `unsupplied` and 1. Aviation — `sortie_t` (4 t aircraft, 1.5 t helicopter) per sortie, from a depot reachable from
  the airfield; an unsupplied airfield launches fewer aircraft.
* **Inflow from the rear** — `supply_inflow` = 2.5 × the side's daily defensive consumption: marching is sustainable,
  combat drains depots. Only to depots reachable from entry points (`supply_entry` of the sector or the 3 own places
  farthest from the front). A cut-off depot (encirclement, destroyed bridges) is supplied only by air.

#### Supply routes and supply convoys

Inflow reaches each depot along its own route — from the nearest entry point over own territory, by road
(`convoys.py`). Route flow — what the depot lacked after daily consumption (within the side's inflow), t/day; leg flow
— the sum of routes through it; trucks — flow / 8 t.

* **In the mission**, on legs with flow of 30 t/day or more within 40 km of the target, truck convoys of both sides
  drive (Ural / KamAZ, M818 / Bedford / Land Rover): 4–16 vehicles — the share of daily flow on the leg during the
  mission (10%), on road to the end of the leg. Each vehicle carries the weight of flow trucks per vehicle.
* **Supply route strike** (`strike_supply_route`, both sides, up to 2 per day): the leg with the highest flow within
  range; package as for a strike.
* **Result.** Destroyed vehicles mean undelivered supply: weight × 8 t; an AI strike outside the mission succeeds
  with 70% minus 10% per SAM in the corridor and causes a 15% shortfall of the leg's daily flow. At end of day the
  shortfall is applied to depots whose routes pass through the leg.

#### Airlift

Task `airlift` for transport aviation (roles `transport`, `transport_helo`); by aircraft — AI only, by helicopter —
the player can fly it (cargo — CTLD crates):

* depots below 90% stock with an own airfield within 40 km, cut-off ones first; up to 4 destinations, 2 runs a day;
* cargo goes only from the rear to the front: the origin is not a helipad and is at least 10 km farther from the
  enemy than the destination;
* cargo per aircraft — `cargo_t` in `aircraft.json` (An-26 5.5 t, C-130 19, Mi-8 4, Mi-26 20, CH-47 10 ...);
* a run inside the mission window is in the mission (up to 2 per side): DCS Transport task; a shot-down aircraft does
  not deliver;
* a player's run delivers what the player actually delivered in CTLD crates (AI wingmen — full load if not shot down).

Airlift volumes are small next to road inflow (tens to hundreds of tonnes vs thousands): they matter where there are
no roads. A depot without its own airfield within 40 km is not supplied by air. Estimates.

#### Explanations for the player

`redfront/explain.py` — "what it is / what it affects / what a strike achieves" lines using the same formulas as the
rear-area model:

* supply route — trucks per day, share of the enemy's inflow, which depots, shortfall after a successful strike;
* depot — capacity (intel), stock (estimate, in quarters), who draws on it, how much burns at a given damage;
* factory — the side's industry multiplier now and after destruction (rear repair, replacements);
* bridge — which links it closes, how much traffic, repair time; airfield — who is based there;
* ground unit — state, combat effectiveness (per intel), break-off threshold; airlift — cargo per run and its share
  of consumption;
* strike result (debrief and AI strikes): stock burned (own — exact, enemy — estimate), industry before and after,
  aircraft available before and after.

### Fog of war and reconnaissance

**Enemy SAMs** (`redfront/intel.py`): the player knows not where a SAM is, but where it was last seen. At campaign
start all positions are known (peacetime intel); after a sortie, enemy SAM positions within 60 km of the player
package's routes are updated. The map, corridor threats and SEAD launch lines use known positions; the mission places
SAMs where they really are. The enemy plans against true positions.

**Enemy ground units** — per the intel log (estimates):

* sources: peacetime intel (at start — all units in place, except reserves from depth); contact (in combat or within
  10 km of own units — always visible); the player's sortie (units within 15 km of the package's routes);
  reconnaissance sorties;
* age: up to 12 h — exact; up to 48 h — approximate (paler, "?", dashed circle of where it could have moved: ~1.2 km/h
  marching, 0.5 km/h stationary); older — presence only ("??"). Old data does not move the front line;
* task targets — known units only: a marching column — data no older than 12 h, a stationary one — approximate data
  too; a column seen marching no more than 18 h ago is tracked by dead reckoning;
* own AI strikes outside the mission: target within 5 km of the aim point — found; beyond 20 km — "target not
  found"; in between — success decreases.

**SAM relocation** (`redfront/samroam.py`, estimates). Only independent SAM sites move (attached air defence moves
with its unit, fixed sites stay). Mobility — by the slowest system in the site:

| Mobility | Systems | Move chance per day near the front | Pause | Step | Area |
|---|---|---|---|---|---|
| high | Osa, Strela, Tunguska, Gepard, Roland, Chaparral | 0.5 | 1 day | 3–6 km | 12 km |
| medium | Kub, Buk, Hawk | 0.3 | 2 days | 4–8 km | 20 km |
| low | Patriot, S-75, S-125, S-200 | 0.08 | 5 days | 5–10 km | 25 km |

The chance is full within 40 km of the enemy and falls to zero at 150 km. The new position stays within the area and
no closer to the front. After losses a mobile SAM moves `sam_relocate_km` to the rear the next day.

#### Air reconnaissance (AI only)

DCS does not model reconnaissance, so the sortie result is computed by the model (`redfront/recon.py`, estimates).
Task `recon` (units with the recon role) is not offered to the player:

* route: points of interest — old data on enemy units, enemy places at and behind the front; up to 4 points no more
  than 60 km apart, within the unit's radius; 3 routes, 2 sorties each (dawn and evening);
* sensors by type (`aircraft.json`, `recon`): swath from the track — photo (day), IR, TV (day), side-looking radar
  (all-weather), ELINT (emitting radars only); profile — low level or high altitude;
* result — one hour after landing: units in the swath are detected (marching column — 0.9, in defence — 0.7). Shot
  down — no data. In the mission — one recon aircraft per side if its route is near the player's strike area;
* enemy reconnaissance is for appearance and losses (its AI knows everything anyway).

| In the OOB | DCS type | Model sensors |
|---|---|---|
| Su-24MR | Su-24MR | photo, IR, TV, SLAR "Shtyk" 25 km, ELINT 150 km |
| MiG-25RB | MiG-25RBT | photo from 20 km (20 km swath, day), ELINT 250 km; high altitude |
| Su-17M3R/M4R (KKR-1) | Su-17M4 | photo, IR, ELINT |
| MiG-21R (R pod) | MiG-21Bis | photo, ELINT |
| RF-4C / RF-4E | F-4E-45MC (or AI F-4E) | photo, IR AN/AAS-18, SLAR AN/APQ-102, ELINT TEREC |
| Tornado GR.1A | Tornado GR4 | IR only (TIRRS), day and night |
| Tornado IDS with pod | Tornado IDS | photo, IR |
| Mirage F1CR | Mirage-F1CR | photo, IR, SLAR Raphael, ELINT ASTAC |
| RF-5E Tigereye | F-5E-3 | photo, IR |
| SF37 | AJS37 | photo, IR |
| F-14A TARPS | F-14A | photo, IR |
| F-16A(R) with Orpheus | F-16A | photo, IR |
| An-30 | An-30M | aerial survey, slow |

### Helicopter air assault

Air assault companies (role `air_assault`): three companies of the 35th Air Assault Brigade for red, two companies of
Fallschirmjägerbataillon 271 for blue — estimates (company — 100 men, 24 infantry figures in the mission). In reserve
(`order reserve`) a company stays at its place.

Task `air_assault` (one per day per side; the player can lead it in a Mi-8 or UH-1H):

* **Where.** An enemy place 8–50 km from own lines, not adjacent to own places, with no enemy units within 10 km. Best —
  the one whose capture cuts off the most enemy depots from rear supply, then the one closest to the own axis
  objective. Landing zone — 2 km from the place toward own lines. The AI does not pick an LZ with more than one SAM in
  the corridor (`max_threats`).
* **With what.** Aircraft = ceil(100 / troops per aircraft) (`troops`: Mi-8 24, Mi-26 80, CH-53 37, CH-47 33,
  UH-1H/UH-60 11), at most 8; groups of 4, the second wave a minute later.
* **In the mission.** Helicopters fly low, land at the LZ for 2 min and return. At mission start the LZ is moved to
  the nearest open spot (`lua/lz.lua`: land, no buildings within 45 m, at most 4 m height difference over 20 m; rings
  up to 1.5 km). Each aircraft unloads its share of figures (`coalition.addGroup`, names from the model; AI aircraft —
  after landing within 800 m of the LZ; player — via CTLD).
* **Result** (`assault.resolve`): player — per debrief; AI — shot down in missions plus 15% per aircraft for each SAM
  in the corridor. The share of the company in lost aircraft dies. Less than 40% arrived — the landing fails, otherwise
  the company holds the place (`order airhead`): takes it if no enemy is near, weakens without supply. Once the place
  is linked to own depots, the company has linked up.

Limitations: forests are not considered when choosing an LZ (DCS exposes only buildings to scripts); AI groups of
other tasks in the mission window fly and land, but their infantry does not dismount.

### Air assault evacuation

Task `air_evac` (priority right after CSAR): a company behind enemy lines (`order airhead`) that has not linked up is
extracted if its effectiveness is below 50% (`evac_below`) or it has held for 3 days or more (`evac_days`). LZ — 1 km
from its place toward own lines; aircraft — enough for the survivors (`troops`), at most 8; no flight through dense air
defence (more than 1 SAM in the corridor). Estimates.

* **In the mission** the company waits near the LZ in groups sized to aircraft capacity (`lua/evac.lua`). An AI
  aircraft picks up its group itself; the player uses CTLD: Troop Transport → Unload / Extract Troops (group within
  125 m). If an aircraft is shot down, its group dies.
* **Result** (`assault.evac_resolve`): anyone extracted — the company goes into reserve near the group's airfield,
  the rest are lost (captured); nobody — the company keeps holding.

### Escort for helicopter tasks

Air assault, evacuation and CSAR fly with attack helicopters (`escort` on the task): a pair, or a flight if there are
more than 4 transports. The escort reaches the LZ 2 min before landing, searches and engages ground targets within
3 km and holds the area while transports are on the ground (+2 min). The nearest attack helicopter unit in range (not
the carrier); none — no escort. Estimates.

### CTLD

[DCS-CTLD](https://github.com/ciribob/DCS-CTLD) 1.6.1 with its bundled MIST is included in the mission only when the
player's sortie needs it. Configuration — `lua/ctld_cfg.lua`; CTLD menus and messages are original (English). Used for:

* **Player air assault.** A loading zone (800 m) at the player's parking spot with an "Assault: <company>" group (the
  company's share on the player's aircraft). F10 → CTLD → Troop Transport → Load; at the LZ — Unload / Extract Troops
  (land or hover for fast-rope). Unloading within 800 m of the LZ counts: the CTLD group is replaced by the company's
  share from the model. Farther — does not count; the group can be picked up and unloaded again.
* **Supply airlift** (helicopter, `airlift`): a supply truck at the parking spot, F10 → CTLD → Crates → Supply — 1000 kg
  crates (500 kg for a light helicopter), up to the aircraft's capacity. Deliver at the destination airfield (2.5 km
  zone): drop or unpack. Delivered kilograms go into the debrief and into the depot at end of day.
* **JTAC** (tasks with `jtac`: strikes on troops in contact, attack helicopters): a post (UAZ-469 / Hummer, invisible
  to enemy AI) near the own platoon closest to the target, 300 m farther from it. Lases targets (code 1688) and marks
  with smoke; F10 → JTAC Status.

Disabled because the model lacks them: FOBs, SAMs and vehicles from crates, beacons, vehicle unpacking. Own code —
CSAR (CTLD has none) and AI troop landing/unloading (`lz.lua`, `assault.lua`).

### Forward arming and refuelling points (FARP)

The ready-made helipads of the Germany map ("H FRG nn", "H GDR nn"; medical and radar ones excluded) are model bases
(`redfront/farp.py`). Ownership — by the owner of the nearest place; enemy within 15 km — closed, within 3 km — lost.
Every day helicopter units move to an own open FARP 15–50 km from the enemy, if it is at least 25 km closer to the
front than the main airfield and no more than 150 km from it; one unit — one FARP (estimates, `farp_*` in `sim`).

A FARP holds from a flight (4) to a squadron (12) — estimate: a forward detachment moves there (a separate unit "...,
forward detachment" with a share of crews and pilots), the rest stays at the airfield. FARP closed, lost or the front
approaches — the detachment returns (not again before the next day). Supply — as for an airfield. Fixed-wing aircraft
do not rebase to FARPs. In the mission helicopters take off from and land at the FARP. A unit rebased by the commander
does not move to FARPs itself while its airfield is intact.

### Crews, pilots and CSAR

**Crews.** An air unit has `crews` crews (establishment — 1.2 per aircraft, `crew_ratio`); sorties are limited by
crews. Replacement — 1 crew per day up to establishment (`crews_per_day`). Aircraft shot down:

* no ejection — crew killed;
* ejected — crew on the ground (`downed`: position, ADF beacon 200–1190 kHz). On own territory they return the next
  day; on enemy territory they are captured with 35% chance per day (`capture_per_day`), after 3 days — missing;
* picked up by a helicopter and delivered to an own airfield — back with the regiment.

**Pilots** (`redfront/pilots.py`): each air unit has a pilot list matching its crews; names are fictional, ranks follow
the unit's nationality (USSR, East Germany, West Germany, USA, UK, Canada, Belgium, Netherlands — by unit name or the
`nation` field). In the mission the aircraft name = rank and surname, the leader is the most senior. A downed pilot is
off the list until rescued; killed or captured pilots leave; replacements get new names.

**Regiment livery** — "Air" → "Pilots, livery"; applies to all the regiment's groups in all missions. The list comes
from the installed DCS (pydcs scans DCS and Saved Games livery folders); if DCS is not found, type the livery folder
name.
Bundled liveries — `redfront/data/liveries.json`: regiment id → {DCS type: livery folder name} (or a string for all
types; `_name` is for reference). Empty means the DCS default. Applied when a campaign is created; a livery set in
the window overrides it. The "Liveries as default" button on the "Air" tab saves the campaign's regiment liveries (`liveries_<theatre>.json`
in the campaigns folder): new campaigns of this theatre get them at once — same regiment, same type (a re-equipped
regiment does not inherit it).

**Task `csar`** (most urgent, up to 2 per day): an own crew not on own territory, nearest helicopter unit in range. The
player can fly a Mi-8 or UH-1H; an AI sortie outside the mission succeeds with 70% minus 15% per SAM in the corridor.

**In the mission** (`lua/csar.lua`, in every mission):

* downed crews from the model (in the task area — both sides) and those who ejected in this mission; immortal and
  invisible to AI — capture is decided by the model; the pilot is moved to the nearest open spot (`lz.lua`, up to
  800 m);
* ADF beacon (AM, kHz); frequencies — in the task, in the menu and in the window;
* helicopter within 3 km — "I hear you"; land within 300 m — the pilot runs to the helicopter; or hover below 20 m
  for 10 s — hoist; once aboard, fly to an own airfield. Helicopter shot down with the pilot aboard — killed;
* F10 menu "CSAR": crew list (bearing, range, frequency), flare, smoke at the nearest.

### Sortie results and DCS AI

* **Non-combat losses of AI helicopters landing in the field are not counted.** The hook records weapon hits
  (`S_EVENT_HIT`); an AI helicopter on a task with an off-airfield landing (air assault, evacuation, CSAR) lost without
  a hit (trees, slope) stays in service. Aircraft and other helicopters that crash without a hit are losses.
* **Result of the player's air assault and evacuation** — what the player actually did; the share of AI wingmen and
  other package groups — per model (not shot down — delivered or extracted its share).
* **Capacity by aircraft type** (`aircraft.json`: `troops`, `cargo_t`): Mi-8 — 24 troops and 4 t, Mi-24P — 8 and 1.5
  t, UH-1H — 11 and 1.5 t; AH-64A, SA342M — none. An attack helicopter regiment can fly air assault, evacuation and
  CSAR if its type carries troops.
* **Humans in a sortie** — "humans N" on the card (`build --humans N`). Seats are filled from the player's group, then
  leaders and wingmen of the other package groups; more than one human — Client slots (multiplayer). Groups with
  humans start cold; human results are theirs, AI — per model.

### Whole theatre in the mission

The mission contains the whole front: the task area in detail, the rest sparser (`materialize.theatre`): battles in
combat formation (own `front.lua` and site per battle), columns on roads, units in defence and in the rear at their
positions, SAMs in full. Density far away — 0.35 of the column budget, one vehicle worth no more than 3 model vehicles
(estimates: `FAR_DENSITY`, `MAX_WEIGHT`). In the whole-map theatre: units within 60 km — partially (up to 24
vehicles), farther — a presence marker (4 vehicles); point air defence — within 100 km of the target
(`materialize.SAM_KM_ROLE`), other SAMs — within 250 km: full sites up to 150 km, beyond that a marker (radars and 2
launchers, launcher weight up to 3 model vehicles; `SAM_FULL_KM`, `SAM_TOKEN_LN`). Organic air defence of units more
than 60 km from the target (not in combat) is not placed; outside the task window attached air defence carries at most
2 radar vehicles (`AD_RADAR_MAX`), the rest are MANPADS, optical SAMs and guns. Site SAM launchers follow the
establishment (SA-2 and SA-5 — 6, SA-3 and SA-6 — 4, HAWK — 6, Patriot — 8), laid out per system (`SITE_LAYOUT`;
estimates). Bubble: all enemy SAMs within `settings.bubble_km` (150 km,
estimate) of the package routes are placed, even if they cannot reach the route — no SEAD group is assigned to them.

#### Mission budget

Ground vehicles in the mission are limited by a budget (default 600, estimate; in settings or `build --budget N`,
stored in the campaign; 0 — unlimited). The player's task window is untouched. The rest is reduced by distance from
the routes and objective, farthest first: columns and formations are thinned first (vehicle weight up to 3 model
vehicles), then distant groups are removed entirely. Removed forces still live in the model. Without a budget a
theatre mission reaches ~1200 vehicles by day 8.

Aircraft in the mission are limited by `settings.mission_air` (settings or `build --air N`; 0 — unlimited, default).
The player package is always placed; then, in order: on-station orbits (AWACS, tanker), AI packages (whole, those near
the player strike first), alert pairs, recon and airlift — while the sortie fits. The cap does not change the air
tasking order: sorties left out of the mission are flown in the model. One orbit shift per zone: the one longest on
station in the mission window holds the zone until the end of the mission.

#### Weather and kneeboard

Weather is per day, with memory (`weather.py`): the regime (high, front, low, post-frontal) follows transition
probabilities from yesterday, adjusted by season; clouds are DCS presets; wind at ground, 2000 and 8000 m; temperature
for the sortie hour; QNH, visibility, rain, morning fog under a high in the cold season. Climate after Hannover
normals (DWD 1961–1990); probabilities and thresholds are estimates. A METAR-style summary goes into the briefing and
the kneeboard, and in the window top bar.

Weather in the air tasking order (`weather.blocks`, minima `weather.MINIMA`, estimates): helicopters — ceiling 150 m,
visibility 1.5 km; visual attack (column, site, landing zone, CSAR) — 600 m and 5 km; photo recon — 1000 m and 5 km;
all-weather types (aircraft.json `night`: Su-24M, Tornado etc.), fighters, AWACS, tankers and airlift — airfield
minima (60 m, 800 m). Checked at takeoff and at the objective; a sortie is moved later (morning fog lifts by
10–11 h) or cancelled if no window is found (logged and shown in the window). Weather settings (⚙ → "Campaign", action `setweather`): climate and season (default), fair only (high pressure
and post-frontal, no fog, cloud base at least 1200 m — e.g. for helicopter flying) or fixed (weather type for every
day and morning fog); the "weather affects the air tasking order" box is `settings.weather_effects`. The campaign
start date is set when creating a campaign (default — the preset date) and can be changed later (`setdate`): it sets
the weather season and mission dates; forces stay as in the preset. After a change the weather is recomputed from
today if nothing has been flown today (the ATO is rebuilt), otherwise from tomorrow.

Kneeboard (`kneeboard.py`, needs Pillow): pages for the player aircraft type — mission (target, threats, package,
sequence, route with times and altitudes), comms, weather and airfields. DCS shows kneeboards per aircraft type, so
pages are labelled with the group.

#### Speed and countries

Group speed on the route and in timing — the doctrine task's `speed_kmh` (estimates); the landing waypoint gets the
same speed (pydcs sets 0, and the AI would otherwise bleed speed on the way home). Countries in the mission — Combined
Joint Task Forces Red / Blue (they have all equipment); unit nationality is in the OOB (`countries`), for the model
and the briefing.

---

## Air war

### Daily air tasking order (ATO)

`redfront/ato.py`: ATO for both sides for the flying day (06:00–20:00, `settings.flying_hours`, estimate).

* The side's tasks in doctrine priority order are spread over the flying day; a sortie is scheduled only if the unit
  has enough aircraft for the whole sortie plus turnaround (`turnaround_min`, default 90 min), otherwise later, in
  15-minute steps.
* Strikes on SAM sites are scheduled before strikes on the targets those SAMs cover (in the corridor or reaching the
  target): the target strike comes at least 30 min after the SAM strike (`ato.SAM_FIRST_MIN`, estimate). Support
  groups (escort, SEAD) are spread across units by their daily load.
* Up to 40 tasks per side per day (`ATO_MAX_TASKS`), at most 8 of one kind (`ATO_PER_KIND`); kinds are interleaved
  (the first of each kind, then the second...) so that aviation is not spent entirely on one kind of task. Estimates.
* Standing tasks (AWACS, tanker, QRA) — 4 h shifts (`shift_h`); without enough aircraft there is a gap.
* Performer — first a suitable and less loaded type and regiment (see [Type suitability](#aircraft-type-suitability)),
  then the nearest: sorties are spread across types and regiments.
* No SAM threats in the corridor (considering radar horizon) — transit and egress at `medium_alt_m_agl` (4000 m,
  estimate), above AAA and MANPADS; with threats — low level.
* **Night.** Only types with `night` in `aircraft.json` fly at night (Su-24M, Tornado, F-15/16, F-4E, MiG-25/29,
  AWACS, tankers, transport, AH-64A; not Su-25, Su-17, MiG-21/23/27, A-10A, AV-8B, Mi-24, SA342M). Standing tasks of
  such types run around the clock; up to 3 of the side's tasks — in the evening (after 20:00, landing by 24:00):
  lower-priority deep strikes and air assaults in which all groups are night-capable. Marked 🌙 in the plan, "NIGHT
  SORTIE" in the briefing. Estimates.

**Mission.** Starts at its own time of day (cold start until the planned takeoff), window `ato.MISSION_LEN_S` (75 min,
estimate). It contains sorties of both sides airborne in that window: at most 3 own groups and 4 enemy groups
(`build.AI_FLIGHTS`), closest in time and place to the player's strike; all standing tasks. Those already en route at
start are airborne on their route, later ones take off on schedule. If one side has fewer than 0.6 of the other's
aircraft in the mission (`build.BALANCE`, estimate), its sorties from the window are added beyond the limit. Squadron
aircraft are never used beyond availability.

**Outside the mission** (`airwar.py`): each sortie of the plan resolves at its time on target. AI strike on a column,
a unit in combat, a SAM site or a rear object: success — 70% minus 10% per SAM in the corridor (× 0.6 + 0.4 × type
suitability); target losses — 4% of equipment per pair (SAM site — 25%), rear object — 25–50% damage. A group loses an
aircraft with 3% per corridor SAM; the crew ejects (70%) near the target and can be rescued. AI groups that were in a
flown mission (`played`) get no off-mission result. Estimates.

Plan: "Sorties" tab; in the console `ato camp.json`, `--side enemy` / `--side all` — enemy plan (debug).

### Packages

A task is flown as a package ('Тактика ВВС' 3.3.3): a strike group and support groups from the doctrine (`strike`
and `support` on the task). Performers are chosen by role, available aircraft and radius. By default the player leads
the strike group (commanding their own flight of up to 4); another group — on the card or `build --fly sead|recon`.
The DCS main task is the first in the doctrine list the type supports (Su-25 has no SEAD — Ground Attack is used).

**Group sizes** (`size`, estimates): WP — strikes on objects, columns, SAMs — flight (4), armed reconnaissance of
supply routes — pair, CAS — flight of attack aircraft, airfield strike escort — flight, SEAD — two pairs; NATO —
object strikes and BAI/FOFA — 4-ship, armed reconnaissance and CAS — pairs, deep strike escort — 4-ship. Too few
serviceable aircraft — a smaller group.

**Rendezvous and sequence.** Groups from different airfields meet at a rendezvous point ("RV", `package.rv_km`, by
default 40 km before the strike group's IP on its airfield–IP line, over own territory), each at its own time: AI
arrives by ETA, the player gets the time in the briefing. From the RV groups push by their lead times (`lead_min`):
SEAD first (straight to its launch line, without the RV), then reconnaissance and escort, strike last (T). The briefing
contains the "Package sequence" (T-4, T-3, T+0). TOT is set by the slowest group: a group that would otherwise be late
takes off at mission start, others later; the player sees "TAKEOFF in N min" (the slot is available from mission
start; taking off early means waiting at the RV).

**Profile.** All waypoints inside known SAM zones are at `low_alt_m_agl` (50 m). Strike, reconnaissance and SEAD
groups are set not to jettison stores. Column speed for prediction — measured in previous missions (`observed_kmh`);
without a measurement the column is assumed stationary. DCS AI below 100 m crashes in turns, so a floor `AI_LOW_MIN_M`
applies to AI aircraft (not helicopters). Numbers are estimates (`estimate_fields`).

**Corridor threat.** A SAM's radius is capped by its radar horizon against a target at route altitude (50 m: ~42 km
with a 10 m antenna, ignoring terrain); otherwise S-200 or Patriot would "reach" any low-level route.

### WP support groups

'Тактика ВВС' 3.3.3; sizes and timings are estimates; only what exists in DCS appears in the mission.

* **SEAD — ARM pair and kill pair.** An ARM pair (Su-24M, Su-17M4, MiG-27K) waits at the launch line; 2 min later a
  kill pair of a different type (Su-17M4, MiG-27K, Su-25 with cluster bombs and rockets) arrives at the same line and
  attacks the SAM. Mandatory if there are SAMs in the corridor: without it the strike is not scheduled.
* **ARM launch line** — `min(standoff_km, SAM radar detection range − detect_margin_km)` from where the SAM will be when
  the group arrives (the ARM homes on emissions). Approach at very low level; at the line — a holding orbit (centre
  pushed toward base by `orbit_radius_km`) at `launch_alt_m` until TOT + `hold_after_min`, with EngageGroup: DCS
  mobile air defence radars switch on as the strike group approaches. If the line is inside the engagement zone — hold
  at low level. SEAD and kill pairs use missile evasion (EvadeFire).
* **Link to intel.** SAM position known precisely (data under 12 h; mobile air defence — per its unit's data; fixed —
  known) — pre-planned launch at the SAM group. No or old data — search and destroy air defence in the area (radius —
  position uncertainty + 5 km). Outside the mission SEAD reduces the strike group's losses from corridor SAMs to 0.5
  (fresh data) or 0.75 (search).
* **Reconnaissance** — if the target is on the march.
* **Sweep** (strikes on airfields, depots, factories, bridges when enemy fighters are present) — a MiG-29 pair
  enters a zone on the approach to the IP 6 min before TOT and holds it until the strike group reaches the target;
  zone outside known SAMs, 6000 m.
* **Escort** — a 40 km zone over the target at 3000 m for TOT + 5 min, if enemy fighters can reach the target.
* **Feint** (strikes on airfields, depots, factories with SAMs in the corridor) — a pair at 6000 m (above Roland and
  Gepard) in another direction (40° from the line to the IP, point outside known SAM zones) 6 min before TOT, 6 min in
  the area.
* No jammers (Yak-28PP, Su-24MP, Mi-8PPA) — they do not exist in DCS.

**AI sorties in the mission fly as full packages:** the strike group and its support groups (SEAD, kill, escort,
sweep, feint) with their own ATO times; the SEAD group only if its SAMs are placed in the mission.

**Strike on SEAD readiness** (`lua/push.lua`). The AI strike group (of the player's package and of every AI sortie, each with its own flag) orbits at the IP until the SEAD group starts
launching; no launches by planned time + 3 min (SAM radars silent) — strike on schedule; SEAD groups shot down
without firing — strike cancelled.

### NATO SEAD

**Hunter-killer.** A hunter pair with ARMs — 52nd Wing (Spangdahlem, F-4G; DCS has no F-4G — F-4E: from 1985 with HARM
on Shrike pylons, the payload from the mission file also works for the player, including on servers with integrity
check; before 1985 — Shrike); 2 min later a killer pair — F-16C of the same wing (before 1987 — F-4E) with
Maverick/cluster bombs attacks the same SAMs. The killer pair only flies with a US hunter pair. From 1990 — German
Tornado ECR (in DCS — Tornado IDS with HARM) and RAF Tornado GR.1 with ALARM (in DCS — GR.4), without a killer pair.
No jammers (EF-111A, EC-130H). Years and composition are estimates.

### Helicopters

* **Helicopter strike on troops in contact** (`cas_helo`): 220 km/h, transit at 60 m, attack from 30 m, IP at 8 km;
  route below 100 m for AI too. Flyable (Mi-24P, SA342M).
* **Attack helicopters fly as flights of 4:** Mi-24P for WP, AH-64A and PAH-1 (SA342M) for NATO. With AH-64A — a pair
  of SA342 scouts (DCS has no OH-58 of that era) reaches the target 3 min earlier and fires only in return.
* **Joint strike** (`joint_heli`; NATO — JAAT, ATP-27(C) 401.4; WP — Mi-24 with Su-25): a helicopter strike and a
  fixed-wing strike (CAS, column strike, BAI) on the same target are merged into one package; helicopters are on target
  2 min before the aircraft.
* **Night:** of the attack helicopters only the AH-64A flies at night.
* **Flying hours** (both sides; FM 101-20, 1984, table 1-5): a helicopter unit flies no more than aircraft × hours per
  month / 30 per day (UH-1H 79, UH-60A 76, OH-58 68, AH-1 65, CH-47 58, CH-54 43 h/month; types without a row — by
  analogue, other helicopters 65 — estimate: no Soviet norms available).
* Transport escort — see [above](#escort-for-helicopter-tasks).

### Fighters, troop cover, QRA

* **Troop cover** — a pair in a zone over own units in combat or on the march, 25 min; flyable.
* **Air defence alert (QRA)** — task `qra` (both sides, AI only): a flight (4) on alert at 5 airfields along the
  front, at least 80 km apart (`qra_bases`, `qra_spacing_km`); only fighter/interceptor units (or types fit for air
  combat) that keep at least one more flight for other tasks; 4 h shifts.
  * **In the mission** flights based within 300 km of the target sit with engines running (late activation).
    `lua/qra.lua` every 10 s looks for enemy aircraft within 200 km of the base and queries own radars (radars, SAM
    radars, AWACS): if a radar sees the target, the flight scrambles, flies to a zone 30 km from base toward the
    front, engages air targets within 80 km, holds 40 min and lands. Low and outside radar coverage — no scramble.
  * **Outside the mission** enemy alert forces within 150 km of an AI strike target reduce its success by 5% and raise
    the loss chance by 4% (`QRA_P`, `QRA_LOSS`). Estimates.
* **GCI:** in DCS only a player in a MiG-29 uses ground control, so a GCI site stands at red airfields where MiG-29s
  are based — by the parking area (150 m from the average parking spot away from the airfield centre). Own channel,
  250 km radius; active from mission start (`ActivateGCI`), channels in the briefing ("Ground control"). GCI is part of
  the model: it can be destroyed, is repaired like a SAM, and is not affected by the mission budget.

### AWACS and tankers

Units with roles `awacs`, `tanker` (whole-map theatre: E-3A — Nörvenich, KC-135 — Ramstein, A-50 — Templin;
estimates) behave like all air units (base, losses, replacements). Orbit task (`method: orbit`, `ai_only`): a zone over
own territory behind the middle of the front at `standoff_km` (AWACS — 150 km, tanker — 200 km; estimates). In every
mission beyond the AI group limit, racetrack from mission start, DCS task AWACS / Tanker; shifts per the plan. Tankers
for blue only: the WP had no tankers for frontal aviation (Il-78 from 1987, for long-range aviation).

### Aircraft type suitability

`aircraft.json`: `fit` — type rating by task kind (0..1, estimates): `cas`, `interdiction` (columns, supply routes),
`strike` (rear objects, SAM sites), `sead`, `air`. Compared with the best type present in the campaign on either side
(`redfront/fitness.py`): the OOB sets the era (Su-25 next to A-10 — 0.85, without it — 1.0).

* Performer choice: relative rating minus 0.15 for each task already given to its type and regiment in this plan;
  below 0.3 — not assigned. SEAD — by `sead`, escort — by `air`.
* AI strike result outside the mission — multiplied by 0.6 + 0.4 × rating.
* A type without `fit` — type is ignored; a rated type lacking the needed kind is unfit for the task (F-15C against rear
  objects).

### Payloads

1. **By task** (`build.loadout_cats`): airfield strike — runway, SAM strike — DEAD, column strike — BAI, depot and
   bridge — strike, cover — CAP; SEAD group — SEAD, strike escort — escort; then the doctrine categories. Source — **DCS
   Retribution** payloads (`data/payloads.json`, 225 types, LGPL-3.0, `data/PAYLOADS_NOTICE.md`, import
   `tools/import_payloads.py`). **Custom payloads** (`data/payloads_custom.json`, same format) come first and replace
   a Retribution payload of the same name (e.g. Su-25 CAS: 2 Kh-25ML, 2 OFAB-250-270, B-8M1 S-8KOM, 2 R-60M). None for
   the type — DCS default loadout.
2. **Mandatory additions** (`weapons.fixups`): Su-24M with ARMs — L-081 "Fantasmagoria" pod on pylon 5 (ARMs cannot be
   launched without it); F-4E — HARM on Shrike pylons (see above).
3. **By campaign year** (`redfront/weapons.py`): the first payload whose weapons all exist in the campaign year is
   used; otherwise weapons newer than the year are replaced by older ones of the same role the pylon can carry
   (AIM-120 → AIM-7 → AIM-9, AGM-65G → D → B, GBU-38 → GBU-12 → Mk-82, CBU-97 → CBU-87 → Mk-20, R-77 → R-27, Kh-31P →
   Kh-58, ALQ-184 → ALQ-131, 9M120 Ataka (from 1996) → 9M114 Shturm ...), otherwise the pylon is empty. Years are
   estimates from open data. Assumption: DCS only has AGM-88C — it represents HARM A/B from 1985. Replacements are shown
   in the briefing ("by year: ...").
4. **Commander's choice:** in the sortie editor — "by task (automatic)" or any Retribution payload of the type; the
   chosen one is adjusted by year the same way.

### Communications

`comms.py`; frequencies are notional, estimate. Nets: package (all player package groups on one frequency), AWACS
(A-50 / E-3A), departure and arrival airfields (DCS ATC frequencies), guard. Red — VHF (124–138 MHz: R-862, R-863,
R-832), blue — UHF (250–264 MHz: ARC-164, ARC-51).

The player aircraft's radio presets are written into the .miz: Ch1 — package, Ch2 — AWACS, Ch3 — departure airfield,
Ch4 — arrival airfield, Ch5 — guard (within the radio's band; F-16 also on VHF). Types without presets in DCS (FC3) —
frequencies in the briefing. The briefing has a comms card and package callsigns; script messages (SEAD started
launching, strike cancelled) are sent as text to the own side.

---

## Doctrines

A doctrine package — `redfront/data/doctrine/<package>.json`, chosen per side (`--doctrine SIDE=PACKAGE`).

| Package | Side | What |
|---|---|---|
| `wp` | red | Warsaw Pact; 'Тактика ВВС', РЛЭ Су-25 (Su-25 flight manual) and others |
| `nato` | blue by default | NATO on the Central Front 1970–1990; generated by `tools/gen_nato.py` |
| `generic` | any | generic profile (`--doctrine blue=generic`) |

**Task structure** (main fields): `title`, `performers` (roles), `target`, `method`, `strike` (strike group: `size`,
`maintask`, `loadout`), `support` (support groups: `size`, `lead_min`, `when`), `speed_kmh`, altitudes
(`transit_alt_m_agl`, `attack_alt_m_agl`, `low_alt_m_agl`, `medium_alt_m_agl`), `ip_offset_km`, `package.rv_km`,
`escort`, `joint_heli`, `jtac`, `ai_only`, `from_year`, `depth_km`, `nations`, `source` / `method_source`,
`estimate_fields`. Package level: `apportionment`, `nation_bonus`, the `sim` section (ground model, supply, FARP, night,
SAM repair), `*_note` explanations.

### NATO doctrine

`data/doctrine/nato.json` (generated by `tools/gen_nato.py`) based on: RAND R-3385-AF (D. Stein, "The Development of
NATO Tactical Air Doctrine 1970-1985", 1987), ATP-27(C) "Air Interdiction and Close Air Support" (1999), AJP-3.3(B)
(2016, apportionment format), FM 100-103 (1987), FM 101-20 (1984). Page references are in `source` /
`method_source`. Altitudes, speeds and group sizes are estimates.

* **Tasks**: CAS (short of the FSCL, ~20–30 km), **BAI** — columns 15–50 km out (ATP-27(B), from 1980; NORTHAG
  priority), DCA, OCA, SAM strikes, **FOFA** — second echelons 50–150 km out (SACEUR directive 1983; depth — estimate),
  supply routes, bridges, depots. Tasks not yet existing in the campaign year are not planned (`from_year`).
* **Apportionment** (`apportionment`): DCA / OCA / SEAD / APCLO — no more than their share of the daily plan (AJP-3.3
  format; shares — estimate: support of ground forces 50%, 60% from day 4).
* **SEAD**: for the allies a supporting action without own assets; a SEAD group only from suitable US units (F-16,
  F-4G), otherwise the package goes without it ("faster and lower"); from 1990 — Tornado ECR/ALARM.
* **National preferences** (`nation_bonus`): UK, West Germany, Belgium, Netherlands (2 ATAF) — CAS and BAI; USA
  (4 ATAF) — air superiority, deep strikes, SEAD. Values — estimate.
* **Altitudes** (FM 100-103, fig. 2-5, LLTR/MRR): ingress at 30 m (100 ft), egress at 150 m; DCS AI no lower than 100 m.

---

## Orders of battle and theatre

### Theatres

* **Hamburg** — `sector_hamburg.json` + `oob_hamburg.json` (console default): operation objectives Lüneburg, Winsen,
  Soltau; variants `base`, `uelzen`, `blue_early`; reserves — a blue armoured brigade (day 4), a red second-echelon tank
  regiment (day 5).
* **Whole map** — `sector_germany.json` + `oob_germany*.json` (generated by `tools/gen_germany.py`): the inner German
  border from Lübeck to Hof, 113 places, 44 military airfields, ~30 WP divisions and ~60 NATO brigades with
  reinforcements, air regiments, the HAWK/Patriot belt. Source of garrisons and aviation — the Germany_OOB_1989 OOB
  mission (`source` field); NATO brigade compositions, reserve timing, axes, DCS substitute types — estimates. Red
  attacks along 8 axes. Window: "New" → "Theatre". Map and road probes are per theatre (`map_germany.json`,
  `roads_germany.json`).

### Fixed air defence

A site is a location and a tier (`ad_sites` in `sector_germany.json`: long / medium / short); what stands there is the
side's template (`ad_templates` in `oob_germany.json`); the unit is created on `new`. Rules (`tools/gen_germany.py`,
estimates): point air defence (Osa/ZSU-23-4 or S-60; Roland/Gepard) at every military airfield; for red — an
S-75/S-125 network covering airfields and places (within 35 km of each, not right at the border) and S-200 in depth;
for blue — the HAWK/Patriot belt. The tier idea comes from the Cold War Germany mission framework; positions and types
were not copied. Sites are not on airfields or in towns: near an airfield — 5 km toward the front, near a place — 3 km
toward the front, S-200 — 4 km to the rear, at least 3 km from any airfield. Sites are read from the sector file on
every load.

Daily (`logistics.air_defence`, estimates): SAM losses are repaired at `repair_sam` (× industry and supply; not for
attached air defence of a unit in combat). Fixed air defence (`fixed`) does not relocate. Task "SAM site strike"
(`strike_sam_site`): target — a serviceable enemy fixed air defence site; priority after airfield strikes.

### Presets by year

Whole-map aviation follows a summary of air forces in Germany (`AIR_HISTORY` in `tools/gen_germany.py`; entries with
"?" — sources disagree, see `source`). The campaign date is the preset date.

* `oob_germany.json` — 1989 (1 September, after the July 1989 rotations), default;
* `oob_germany_1987.json` — 1987 (1 June): MiG-29 in 4 of 9 fighter regiments, Brand on Su-24M;
* `oob_germany_1985.json` — 1985 (1 June): no MiG-29, no Su-25.

A historical type missing from DCS is replaced by the nearest (MiG-23M → MiG-23MLD, Su-17M3 → Su-17M4, F-16A/C block
15–30 → F-16C block 50, F-104G → F-4E etc.). Aircraft numbers and radii are estimates. Ground forces are the same in all
presets.

Units based off the Cold War Germany map are **relocated** to own-side airfields on the map (`relocate` in the
generator): the airfield closest to the real base, empty ones first, by pydcs parking capacity; each unit of the same
class "lengthens" the distance by 300 km; regiment sub-units stay together. Main ones:

| Unit | Real base | On the map |
|---|---|---|
| 497 бап (Su-24) | Großenhain | Sperenberg |
| 296 апиб (MiG-27) | Altenburg | Cochstedt |
| 559 апиб (MiG-27K) | Finsterwalde | Briest |
| 11 орап (Su-24MR) | Welzow | Mahlwinkel |
| 336 обвп (Mi-24, Mi-8) | Nohra | Obermehler Schlotheim |
| JG-3 NVA (MiG-29, MiG-21) | Preschen | Stendal (+ GCI) |
| JBG-37, JG-7 NVA | Drewitz | Parchim, Marxwalde |
| KHG-3, KHG-5 NVA (Mi-24, Mi-8) | Cottbus, Basepohl | Brand, Tutow |
| RAF: Phantom / Tornado / 2 sqn | Wildenrath / Brüggen / Laarbruch | Wiesbaden / Frankfurt, Buckeburg / Wunstorf |
| JaboG 32 / 34 / 38 / 36 (Tornado, F-4F) | Lechfeld / Memmingen / Jever / Hopsten | Giebelstadt / Sembach / Nordholz / Fassberg |
| JG 71 / JG 74 (F-4F) | Wittmundhafen / Neuburg | Kiel / Giebelstadt |
| JaboG 43 / 44 / 49 (Alpha Jet → L-39ZA) | Oldenburg / Leipheim / Fürstenfeldbruck | Nordholz / Sembach / Frankfurt |
| AG 51 (RF-4E), 4 Wing Canada (CF-18) | Bremgarten, Baden-Söllingen | Ramstein, Pferdsfeld |
| A-10 forward operating locations | Ahlhorn, Jever | Wunstorf, Fassberg |

Full list — `_relocated` in the preset file. Transport (`transport`, `transport_helo`) — on both sides: 226 осап (An-26,
Mi-8) Sperenberg, 239 овп (Mi-26, Mi-8) Oranienburg, Mi-8 squadrons of the обвп, THG-34 Briest, TFG-44; RAF 18 and
230 sqn Gütersloh, LTG 61/62/63 (C-130 instead of Transall), US Army UH-60A, Heeresflieger CH-53. Attack helicopters
(`attack_helo`): Mi-24P regiments of the GSFG armies (Parchim, Mahlwinkel, Brandis, Allstedt), PAH-1 (SA342M) — Celle,
Fritzlar, AH-64A — Giebelstadt (estimates). Not included (`_not_included`): training regiments, 968 иап, combat-control
helicopters, EW units, Belgian and Dutch units.

### Add regiment, rebase

"Air" → "Add regiment" (`redfront/reinforce.py`), at any time:

* **from the list** — air units of other presets of the same theatre not present in this campaign (historical
  assumption): e.g. the 116th Guards and 497th bomber regiments (Su-24M) left Germany in July 1989 and are absent from
  the 1989 preset; airfield — its own from the preset (if held by the enemy — the nearest own);
* **custom regiment** — name, side, role, aircraft type (any pydcs aircraft), count, airfield (helicopters — also a
  FARP), radius (empty — by role, otherwise estimate 300 km, helicopters 150).

In the window the unit is marked "assumption" or "custom". It enters the plan from the next day.

"Air" → own unit → "Rebase": own open airfields with space (16 slots per regiment; helicopters — also FARPs), with
distance to the enemy. The order is executed at end of day and can be cancelled.

---

## Data and files

### `redfront/data`

| File | What |
|---|---|
| `doctrine/wp.json`, `nato.json`, `generic.json` | doctrine packages |
| `oob_hamburg.json`, `oob_germany.json`, `oob_germany_1987.json`, `oob_germany_1985.json` | orders of battle |
| `sector_hamburg.json`, `sector_germany.json` | sectors |
| `roles.json` | roles and categories |
| `aircraft.json` | aircraft type properties: `night`, `troops`, `cargo_t`, `recon`, `fit` |
| `payloads.json`, `PAYLOADS_NOTICE.md` | DCS Retribution payloads (LGPL-3.0) |
| `payloads_custom.json` | custom payloads |

### Python modules (`redfront/`)

| Module | Purpose |
|---|---|
| `model.py` | data layers, roles, doctrine package, strength, route, save |
| `dcstypes.py` | pydcs type lookup, SAM range |
| `sim.py` | hourly ground model |
| `ops.py` | operational level: command decisions |
| `logistics.py`, `convoys.py` | supply, depots, supply routes, daily air defence |
| `planner.py`, `ato.py`, `command.py` | tasks and packages, ATO, commander mode |
| `airwar.py`, `assault.py`, `recon.py` | off-mission sortie results, air assault/evacuation, reconnaissance |
| `intel.py`, `samroam.py` | fog of war, SAM relocation |
| `fitness.py`, `weapons.py`, `comms.py` | type suitability, payloads by year, communications |
| `farp.py`, `pilots.py`, `reinforce.py` | FARPs, pilots, adding regiments |
| `explain.py`, `symbols.py` | explanations, map symbol classification |
| `materialize.py`, `build.py` | mission deployment, .miz build |
| `debrief.py` | hook file → model |

### Lua scripts (`redfront/lua/`)

| Script | Purpose |
|---|---|
| `debrief_hook.lua` | writes losses, hits, landings, positions, roads, battle sites to JSON |
| `front.lua` | troops-in-contact battle |
| `battle_site.lua` | placing battles and air defence on terrain |
| `column_road.lua` | moving a column onto the road |
| `targets.lua` | map objects as targets |
| `push.lua` | strike on SEAD readiness |
| `qra.lua` | QRA scramble on detection |
| `lz.lua` | choosing an open landing spot |
| `assault.lua`, `evac.lua` | troop landing, evacuation |
| `csar.lua` | combat search and rescue |
| `ctld_cfg.lua`, `ctld/` | DCS-CTLD configuration and distribution |
| `map_probe.lua`, `roads_probe.lua` | map and road utility probes |

### Tools (`tools/`)

`gen_germany.py` (whole-map theatre and presets), `gen_nato.py` (`nato.json`), `import_payloads.py` (Retribution
payloads), `smoke_test.py` (test).

---

## Verified / not verified

* **Without DCS:** the .miz builds and is re-read by pydcs; the Lua hook runs in a Lua interpreter with DCS API stubs
  and writes valid JSON; losses and advance are applied; the second day builds (`tools/smoke_test.py`). Another type
  with the same role (A-10A) is planned and built; a side without a doctrine package yields a reason instead of a task.
  The test has passed on a machine with DCS (Python 3.15, no lupa): DCS default loadouts, liveries from Saved Games.
* **Verified in DCS:** the hook writes its file to `Saved Games\DCS\redfront`, losses and landings are recorded, the
  mission ends normally; columns drive; Patriot facing the threat axis engages; moving a column onto the road works
  (the group is replaced keeping groupId); the package flies. Without roads a column in a field breaks up in DCS.
* **Not verified in DCS:** the roads probe (tested only with `land.*` / `coalition.addGroup` stubs); the two-pair SEAD
  scheme with a launch line and low level in SAM zones; column air defence (Gepard, Roland) and Patriot in depth. OOB
  changes only reach new campaigns (`new`).

---

## Tests

    .venv\Scripts\python tools\smoke_test.py      # test without DCS
    .venv\Scripts\python -m pytest -q              # the same under pytest (tests/test_smoke.py), each section a separate test

For pytest and the full Lua hook check: `.venv\Scripts\python -m pip install -r requirements-dev.txt` (installs
lupa). If pip cannot build lupa, the test runs without it, skipping 4 hook checks. On GitHub the tests run on every
push and pull request (`.github/workflows/tests.yml`).

---

## Credits and licences

* The "mission hook writes JSON, the application reads it" approach and the `DoScript(String(...))` note come from
  [SQE](https://github.com/MarkuzJuniuz/SQE) (MIT, MarkuzJuniuz). The code was written from scratch.
* CSAR mechanics (ADF beacon, smoke and flare on request, pilot runs to the helicopter, hoist, delivery to an airfield)
  are inspired by [DCS-CSAR](https://github.com/ciribob/DCS-CSAR) (ciribob). The repository has no licence, so no code
  is copied: `lua/csar.lua` was written from scratch, without MIST.
* [DCS-CTLD](https://github.com/ciribob/DCS-CTLD) (Ciribob, Zip, VEAF; "free of use… publish a fork… credit
  appreciated") and its bundled MIST (Speed, Grimes, lukrop) are in `redfront/lua/ctld/` unmodified; source and versions
  — `redfront/lua/ctld/NOTICE.md`.
* The troops-in-contact battle idea — Troops in Contact script (Grendel, MIT); own code.
* Payloads — DCS Retribution, LGPL-3.0 (`redfront/data/PAYLOADS_NOTICE.md`).
