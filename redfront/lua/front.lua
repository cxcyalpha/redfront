-- redfront front | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Бой наземных частей в миссии. Идея взята у Troops in Contact (Grendel, MIT): ИИ DCS бьёт по наземным целям
-- снайперски, бой кончается за минуты. Здесь - по-своему, без MOOSE, невидимости и пересоздания групп:
--   * взводы (группы по несколько машин) по умолчанию огонь не ведут (ROE "огонь запрещён");
--   * раз в period_min..period_max с каждый взвод получает короткое окно огня (burst_s) и задачу FireAtPoint -
--     в точку в aim_min..aim_max м от случайной живой машины противника в пределах дальности своего оружия;
--     затем снова запрет огня. Шум и трассы боя есть, потерь мало (их считает модель кампании);
--   * опцию "цели только наземные" (28) скрипт не трогает: по самолётам стреляет только ПВО (её здесь нет);
--   * наступающий взвод при потерях формирования в миссии ниже retreat_below отходит на исходную;
--   * обороняющиеся взводы раз в shift_min..shift_max с сдвигаются на несколько десятков метров - позиции "живут".
-- Все числа - ОЦЕНКИ (build.py, FRONT_CFG).

REDFRONT_FRONT_LOG = REDFRONT_FRONT_LOG or {}

local CFG = @CFG@
local PLATOONS = { @PLATOONS@ }

local ROE = AI.Option.Ground.id.ROE
local HOLD = AI.Option.Ground.val.ROE.WEAPON_HOLD
local OPEN = AI.Option.Ground.val.ROE.OPEN_FIRE

local byName, formations = {}, {}
for _, p in ipairs(PLATOONS) do
  byName[p.name] = p
  formations[p.formation] = formations[p.formation] or { platoons = {}, start = 0, retreated = false, attack = p.attack }
  table.insert(formations[p.formation].platoons, p)
end

local function now() return timer.getTime() end
local function rnd(a, b) return a + math.random() * (b - a) end

local function aliveUnits(name)
  local g = Group.getByName(name)
  if not g or not g:isExist() then return {} end
  local out = {}
  for _, u in ipairs(g:getUnits() or {}) do
    if u and u:isExist() and u:getLife() > 0 then out[#out + 1] = u end
  end
  return out
end

local function center(units)
  local x, z = 0, 0
  for _, u in ipairs(units) do local p = u:getPoint(); x = x + p.x; z = z + p.z end
  return { x = x / #units, z = z / #units }
end

local function route(name, x, y, speed)
  local g = Group.getByName(name)
  if not g then return end
  g:getController():setTask({ id = "Mission", params = { route = { points = {
    { x = x, y = y, type = "Turning Point", action = "Off Road", speed = speed, ETA = 0, ETA_locked = false, speed_locked = true } } } } })
end

local function burst(p)
  local own = aliveUnits(p.name)
  if #own == 0 then return end
  local c = center(own)
  local targets = {}
  for _, en in ipairs(p.enemies) do
    for _, u in ipairs(aliveUnits(en)) do
      local q = u:getPoint()
      if (q.x - c.x) ^ 2 + (q.z - c.z) ^ 2 <= p.range ^ 2 then targets[#targets + 1] = q end
    end
  end
  if #targets == 0 then return end
  local t = targets[math.random(#targets)]
  local a, r = rnd(0, 2 * math.pi), rnd(CFG.aim_min, CFG.aim_max)
  local ctl = Group.getByName(p.name):getController()
  ctl:setOption(ROE, OPEN)
  ctl:pushTask({ id = "FireAtPoint", params = { point = { x = t.x + r * math.cos(a), y = t.z + r * math.sin(a) },
                                                radius = CFG.aim_radius, expendQty = CFG.salvo, expendQtyEnabled = true } })
  p.shots = (p.shots or 0) + 1
  timer.scheduleFunction(function()
    local g = Group.getByName(p.name)
    if g and g:isExist() then
      local c2 = g:getController()
      c2:setOption(ROE, HOLD)
      pcall(function() c2:popTask() end)
    end
    return nil
  end, nil, now() + CFG.burst_s)
end

local function strength(f)
  local n = 0
  for _, p in ipairs(f.platoons) do n = n + #aliveUnits(p.name) end
  return n
end

-- Начало - через init_s: сначала battle_site.lua переставляет взводы по местности (пересоздание групп).
local function init()
-- начальное состояние: огонь запрещён, исходные позиции запомнены
for name, f in pairs(formations) do
  f.start = strength(f)
  for _, p in ipairs(f.platoons) do
    local own = aliveUnits(p.name)
    if #own > 0 then
      p.home = center(own)
      Group.getByName(p.name):getController():setOption(ROE, HOLD)
    end
  end
end

-- огонь: у каждого взвода своё расписание
for _, p in ipairs(PLATOONS) do
  timer.scheduleFunction(function()
    pcall(burst, p)
    return now() + rnd(CFG.period_min, CFG.period_max)
  end, nil, now() + rnd(CFG.first_min, CFG.period_max))
end

-- отход наступающих при потерях; "живые" позиции обороняющихся
timer.scheduleFunction(function()
  for name, f in pairs(formations) do
    if f.attack and not f.retreated and f.start > 0 and strength(f) < f.start * CFG.retreat_below then
      f.retreated = true
      for _, p in ipairs(f.platoons) do
        if p.home and #aliveUnits(p.name) > 0 then route(p.name, p.home.x, p.home.z, CFG.retreat_speed) end
      end
      REDFRONT_FRONT_LOG[name] = string.format("отход на исходную на %d с: в строю %d из %d", math.floor(now()), strength(f), f.start)
      env.info("redfront front " .. name .. ": " .. REDFRONT_FRONT_LOG[name])
    end
  end
  return now() + CFG.check_s
end, nil, now() + CFG.check_s)

local function shift()
  local defenders = {}
  for _, p in ipairs(PLATOONS) do
    if not p.attack and p.home and #aliveUnits(p.name) > 0 then defenders[#defenders + 1] = p end
  end
  if #defenders > 0 then
    local p = defenders[math.random(#defenders)]
    local a, r = rnd(0, 2 * math.pi), rnd(0, CFG.shift_m)
    route(p.name, p.home.x + r * math.cos(a), p.home.z + r * math.sin(a), CFG.shift_speed)
  end
  return now() + rnd(CFG.shift_min, CFG.shift_max)
end
timer.scheduleFunction(function() pcall(shift); return now() + rnd(CFG.shift_min, CFG.shift_max) end, nil, now() + CFG.shift_min)
env.info(string.format("redfront front: %d взводов", #PLATOONS))
end

timer.scheduleFunction(function() local ok, e = pcall(init); if not ok then env.warning("redfront front: " .. tostring(e)) end; return nil end,
                       nil, now() + CFG.init_s)
