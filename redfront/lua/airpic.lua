-- redfront airpic | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Общая картина воздушной обстановки сторон для qra.lua (подъём дежурных звеньев) и gci.lua (наведение): самолёты и
-- вертолёты противника, которых видят НАЗЕМНЫЕ РЛС стороны (РЛС обнаружения и РЛС обнаружения ЗРК; видимость -
-- модель DCS: радиогоризонт, рельеф, малая высота). Одна картина на сторону за PIC_S секунд (оба скрипта берут её из
-- кэша), список РЛС - раз в RADAR_S; нет противника в воздухе - РЛС не опрашиваются.
-- Ценность и курс цели (как решает пункт наведения): ударные, ДРЛО и заправщики - 3, многоцелевые - 2, истребители -
-- 1, вертолёты - по доктрине (heli); идёт к своему объекту (аэродром, ЗРК: PROTECT) - inbound.
RF_AIR = RF_AIR or {}
local PIC_S, RADAR_S, RAID_M = 10, 60, 15000
local RADAR_ATTR = { "EWR", "SAM SR" }
RF_AIR.PROTECT = { @PROTECT@ }       -- [сторона] = { {x, y}, ... }
local radarCache, picCache, tracks = {}, {}, {}
local TRACK_S, GAP_S = 30, 25      -- ОЦЕНКА: устойчивое сопровождение - 30 с, разрыв до 25 с (3 обзора) не сбрасывает

local function d2(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.z - b.z) ^ 2) end
RF_AIR.d2 = d2

local function radars(side, awacs)    -- awacs - и самолёты ДРЛО (подъём звеньев НАТО), иначе только наземные (наведение)
  local now, key = timer.getTime(), side .. (awacs and "a" or "g")
  local c = radarCache[key]
  if c and now - c.t < RADAR_S then return c end
  local ctrl, pos = {}, {}
  local cats = awacs and { Group.Category.GROUND, Group.Category.AIRPLANE } or { Group.Category.GROUND }
  for _, cat in ipairs(cats) do
    for _, g in ipairs(coalition.getGroups(side, cat) or {}) do
      for _, u in ipairs(g:getUnits() or {}) do
        local ok = false
        if u and u:isExist() then
          for _, a in ipairs(RADAR_ATTR) do if u:hasAttribute(a) then ok = true end end
          if cat == Group.Category.AIRPLANE then ok = u:hasAttribute("AWACS") end
        end
        if ok then ctrl[#ctrl + 1] = g:getController(); pos[#pos + 1] = u:getPoint(); break end   -- одна РЛС на группу
      end
    end
  end
  c = { t = now, ctrl = ctrl, pos = pos }
  radarCache[key] = c
  return c
end

local function foesAirborne(side)
  local foe = side == 1 and 2 or 1
  for _, cat in ipairs({ Group.Category.AIRPLANE, Group.Category.HELICOPTER }) do
    for _, g in ipairs(coalition.getGroups(foe, cat) or {}) do
      for _, u in ipairs(g:getUnits() or {}) do
        if u and u:isExist() and u:inAir() then return true end
      end
    end
  end
  return false
end

function RF_AIR.picture(side, awacs)   -- { list = единицы, seen = имя -> true, rpos = позиции РЛС }
  local now, key = timer.getTime(), side .. (awacs and "a" or "g")
  local p = picCache[key]
  if p and now - p.t < PIC_S then return p end
  local seen, list = {}, {}
  local raw = {}
  local r = radars(side, awacs)
  if foesAirborne(side) then
    for _, c in ipairs(r.ctrl) do
      local ok, dets = pcall(function() return c:getDetectedTargets(Controller.Detection.RADAR) end)
      for _, d in ipairs(ok and dets or {}) do
        local o = d.object
        if o and o.isExist and o:isExist() and o.getCoalition and o:getCoalition() ~= side and o.inAir and o:inAir() then
          raw[o:getName()] = o
        end
      end
    end
  end
  -- сопровождение: цель - в картине, только если РЛС держат её не меньше TRACK_S (разрывы короче GAP_S - не сброс);
  -- засветка на секунду (горка над хребтом) тревоги и наведения не даёт - маловысотный профиль работает
  local tr = tracks[key] or {}
  for n, o in pairs(raw) do
    local t = tr[n]
    if not t or now - t.last > GAP_S then t = { first = now } end
    t.last = now
    tr[n] = t
    if now - t.first >= TRACK_S and not seen[n] then seen[n] = true; list[#list + 1] = o end
  end
  for n, t in pairs(tr) do if now - t.last > GAP_S then tr[n] = nil end end
  tracks[key] = tr
  p = { t = now, list = list, seen = seen, rpos = r.pos }
  picCache[key] = p
  return p
end

local function has(u, a) local ok, r = pcall(function() return u:hasAttribute(a) end); return ok and r end

function RF_AIR.value(t, heli)       -- ценность цели: 0 - не перехватываем
  if has(t, "Helicopters") then return heli and 1 or 0 end
  if has(t, "AWACS") or has(t, "Tankers") then return 3 end
  if has(t, "Bombers") or has(t, "Strategic bombers") then return 3 end
  if has(t, "Fighters") or has(t, "Interceptors") then return 1 end
  if has(t, "Multirole fighters") then return 2 end   -- F-4, F-16 - чаще всего ударная группа
  return 2
end

function RF_AIR.inbound(side, t)     -- цель идёт к своему объекту (вектор скорости - на ближний объект ближе 60 град.)
  local p, v = t:getPoint(), t:getVelocity()
  local sp = math.sqrt(v.x ^ 2 + v.z ^ 2)
  if sp < 30 then return false end
  local best, bd = nil, math.huge
  for _, o in ipairs(RF_AIR.PROTECT[side] or {}) do
    local d = math.sqrt((o.x - p.x) ^ 2 + (o.y - p.z) ^ 2)
    if d < bd then best, bd = o, d end
  end
  if not best then return false end
  return ((best.x - p.x) * v.x + (best.y - p.z) * v.z) / (bd * sp + 1) > 0.5
end

function RF_AIR.raids(side, heli, awacs)   -- налёты: идущие к своим объектам самолёты, сгруппированные ближе RAID_M
  local out = {}
  for _, t in ipairs(RF_AIR.picture(side, awacs).list) do
    if RF_AIR.value(t, heli) > 0 and RF_AIR.inbound(side, t) then
      local p, raid = t:getPoint(), nil
      for _, r in ipairs(out) do if d2(r.pos, p) <= RAID_M then raid = r; break end end
      if raid then raid.n = raid.n + 1 else out[#out + 1] = { pos = p, n = 1, lead = t } end
    end
  end
  return out
end
