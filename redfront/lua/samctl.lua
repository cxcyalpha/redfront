-- redfront samctl | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Управление огнём ПВО поверх ИИ DCS (ОЦЕНКИ):
--   1. Реакция: от первого обнаружения цели своей РЛС (или оптикой) до разрешения огня - delay (зависит от типа ЗРК,
--      выучки расчёта и тревоги: держали цель недавно - быстрее). До этого - огонь запрещён (ROE WEAPON_HOLD).
--   2. Дальность: огонь - только по цели ближе k_range x зоны поражения (не пуск на предельной дальности).
--   3. Зенитная артиллерия: заградительный огонь (FireAtPoint на высоте цели, с упреждением, с разбросом) вместо
--      прицельного - огонь по самолётам ИИ DCS запрещён; заграждение ставится по ближней цели раз в BARRAGE_S.
--   4. Стрельба с переездом (подвижные ЗРК: Куб, Оса...): после SCOOT_SHOTS пусков - РЛС выключены, переезд на
--      SCOOT_M и тишина SCOOT_MIN..SCOOT_MAX с (iads.lua не включает их на это время).
--   6. ПЗРК: огонь - по цели ближе MANPAD_M и медленнее MANPAD_V, не больше MANPAD_SHOTS пусков на группу за миссию.
-- Итог - REDFRONT_SAMCTL (хук пишет в дебриф).
REDFRONT_SAMCTL = REDFRONT_SAMCTL or { scoot = {}, events = {} }
local CHECK_S, BARRAGE_S, FORGET_S = 2, 8, 90
local SCOOT_SHOTS, SCOOT_M, SCOOT_MIN, SCOOT_MAX = 2, 1500, 300, 600
local MANPAD_M, MANPAD_V, MANPAD_SHOTS = 4500, 300, 2
local SPECS = { @SPECS@ }   -- { group, kind = sam|aaa|manpad, r (м), k_range, delay (с), mobile }
local st = {}               -- группа -> { first, last, open, shots, scoot_until }

local function grp(n) local g = Group.getByName(n); if g and g:isExist() then return g end end
local function lead(g)
  for _, u in ipairs(g:getUnits() or {}) do if u and u:isExist() and u:getLife() > 0 then return u end end
end
local function d2(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.z - b.z) ^ 2) end
local function setROE(g, open)
  pcall(function()
    g:getController():setOption(AI.Option.Ground.id.ROE,
      open and AI.Option.Ground.val.ROE.OPEN_FIRE or AI.Option.Ground.val.ROE.WEAPON_HOLD)
  end)
end
local function note(s, what) local e = REDFRONT_SAMCTL.events; e[#e + 1] = { group = s.group, what = what, t = math.floor(timer.getTime()) } end

local function targets(g)
  local out = {}
  local ok, list = pcall(function() return g:getController():getDetectedTargets() end)
  for _, d in ipairs(ok and list or {}) do
    local o = d.object
    if o and o.isExist and o:isExist() and o.getCategory and o:getCategory() == Object.Category.UNIT and o.inAir and o:inAir() then
      out[#out + 1] = o
    end
  end
  return out
end

local function barrage(g, u, o, s)
  local p, v = o:getPoint(), o:getVelocity()
  local d = d2(p, u:getPoint())
  local tof = d / 900                                    -- ОЦЕНКА: полёт снаряда ~900 м/с
  local aim = { x = p.x + v.x * tof, y = p.z + v.z * tof }
  local r = 150 + d * 0.05                               -- разброс растёт с дальностью
  pcall(function()
    g:getController():pushTask({ id = "FireAtPoint", params = { point = aim, radius = r, expendQty = 40,
      expendQtyEnabled = true, altitude = p.y, alt_type = 0 } })
  end)
end

local function scoot(g, u, s, now)
  local p = u:getPoint()
  local a = math.random() * 2 * math.pi
  local to = { x = p.x + math.cos(a) * SCOOT_M, y = p.z + math.sin(a) * SCOOT_M }
  pcall(function()
    g:getController():setOption(AI.Option.Ground.id.ALARM_STATE, AI.Option.Ground.val.ALARM_STATE.GREEN)
    g:getController():setTask({ id = "Mission", params = { route = { points = {
      { x = p.x, y = p.z, type = "Turning Point", action = "Off Road", speed = 10 },
      { x = to.x, y = to.y, type = "Turning Point", action = "Off Road", speed = 10 } } } } })
  end)
  local quiet = SCOOT_MIN + math.random() * (SCOOT_MAX - SCOOT_MIN)
  REDFRONT_SAMCTL.scoot[s.group] = now + quiet
  note(s, "scoot")
end

local function check()
  local now = timer.getTime()
  for _, s in ipairs(SPECS) do
    local g = grp(s.group)
    local u = g and lead(g)
    if u then
      local c = st[s.group] or { first = nil, last = -1e9, open = nil, shots = 0, b = 0 }
      st[s.group] = c
      local up = u:getPoint()
      local best, bd = nil, math.huge
      for _, o in ipairs(targets(g)) do
        if o:getCoalition() ~= u:getCoalition() then
          local d = d2(o:getPoint(), up)
          if d < bd then best, bd = o, d end
        end
      end
      if best then
        if not c.first or now - c.last > FORGET_S then c.first = now end
        c.last = now
      end
      local open = false
      if (REDFRONT_SAMCTL.scoot[s.group] or 0) > now then
        open = false                                      -- переезд: молчим
      elseif s.kind == "manpad" or s.kind == "aaa" then
        local v = best and best:getVelocity()
        local spd = v and math.sqrt(v.x ^ 2 + v.y ^ 2 + v.z ^ 2) or 0
        -- ПЗРК (и ПЗРК при зенитках): близкая и не слишком быстрая цель, не больше MANPAD_SHOTS пусков
        open = s.manpad and best ~= nil and c.shots < MANPAD_SHOTS and bd <= MANPAD_M and spd <= MANPAD_V
               and now - c.first >= s.delay or false
      end
      if s.kind == "aaa" and not open then              -- зенитки: прицельно - нет; заграждение
        if best and bd <= s.r and now - c.first >= s.delay and now - c.b >= BARRAGE_S then
          barrage(g, u, best, s)
          c.b = now
        end
      elseif s.kind == "sam" and (REDFRONT_SAMCTL.scoot[s.group] or 0) <= now then
        open = best ~= nil and bd <= s.r * s.k_range and now - c.first >= s.delay
      end
      if open ~= c.open then
        setROE(g, open)
        c.open = open
        if open then note(s, "fire") end
      end
    end
  end
  return now + CHECK_S
end

local H = {}
function H:onEvent(e)
  if e.id ~= world.event.S_EVENT_SHOT or not e.initiator then return end
  local ok, gn = pcall(function() return e.initiator:getGroup():getName() end)
  if not ok or not gn then return end
  for _, s in ipairs(SPECS) do
    if s.group == gn then
      local c = st[gn] or { shots = 0, last = -1e9, b = 0 }
      st[gn] = c
      c.shots = (c.shots or 0) + 1
      if s.manpad and s.kind ~= "sam" and c.shots >= MANPAD_SHOTS then
        local g = grp(gn); if g then setROE(g, false) end; c.open = false; note(s, "manpad_out")
      elseif s.mobile and c.shots >= SCOOT_SHOTS then
        local g = grp(gn); local u = g and lead(g)
        if u then scoot(g, u, s, timer.getTime()); c.shots = 0; c.open = false; setROE(g, false) end
      end
    end
  end
end
world.addEventHandler(H)
for _, s in ipairs(SPECS) do local g = grp(s.group); if g then setROE(g, false) end end   -- до обнаружения - огонь запрещён
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
