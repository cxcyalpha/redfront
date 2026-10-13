-- redfront column-on-road | campaign @CAMPAIGN@ | sortie @SORTIE@
-- В .miz колонна стоит на расчётной геометрии маршрута (без дорог - на прямой между пунктами, т.е. в поле).
-- В начале миссии этот скрипт спрашивает у DCS путь по дорогам для оставшихся участков маршрута и пересоздаёт
-- группу на дороге (coalition.addGroup) с теми же именами машин и тем же groupId: голова - в ближайшей к расчётной
-- точке дороги, остальные - позади вдоль дороги через spacing метров.
-- Найденные пути кладутся в REDFRONT_ROADS - хук дебрифа пишет их в файл, и модель запоминает дороги.
-- Если DCS дорогу не нашёл или addGroup не сработал - колонна остаётся, где стояла.
REDFRONT_ROADS = REDFRONT_ROADS or {}
REDFRONT_COLUMN_LOG = REDFRONT_COLUMN_LOG or {}
-- Замена группы может породить события гибели старых машин: хук не засчитывает потери колонны до этого времени.
REDFRONT_RESPAWN_UNTIL = timer.getTime() + 5

local COLUMNS = { @COLUMNS@ }
local atan2 = math.atan2 or math.atan        -- DCS: Lua 5.1 (math.atan2); в Lua 5.3+ это math.atan(y, x)

local function xy(a, b)            -- API отдаёт точку двумя числами или таблицей {x=, y=}
  if type(a) == "table" then return a.x, a.y end
  return a, b
end

local function roadPath(p, q)
  local ax, ay = xy(land.getClosestPointOnRoads("roads", p.x, p.y))
  local bx, by = xy(land.getClosestPointOnRoads("roads", q.x, q.y))
  if not (ax and bx) then return nil end
  local path = land.findPathOnRoads("roads", ax, ay, bx, by)
  if type(path) ~= "table" or #path < 2 then return nil end
  local out = {}
  for _, r in ipairs(path) do
    local x, y = xy(r)
    out[#out + 1] = { x = x, y = y }
  end
  return out
end

-- расстояние вдоль пути до ближайшей к (hx, hy) точки
local function projectS(path, hx, hy)
  local best, bestS, run = nil, 0, 0
  for i = 1, #path - 1 do
    local a, b = path[i], path[i + 1]
    local dx, dy = b.x - a.x, b.y - a.y
    local L2 = dx * dx + dy * dy
    local t = 0
    if L2 > 0 then t = math.max(0, math.min(1, ((hx - a.x) * dx + (hy - a.y) * dy) / L2)) end
    local px, py = a.x + dx * t, a.y + dy * t
    local d = (px - hx) ^ 2 + (py - hy) ^ 2
    local seg = math.sqrt(L2)
    if best == nil or d < best then best, bestS = d, run + seg * t end
    run = run + seg
  end
  return bestS
end

-- точка и курс на пути через s метров от начала (курс DCS: от севера (x) по часовой, радианы)
local function pointAt(path, s)
  s = math.max(0, s)
  for i = 1, #path - 1 do
    local a, b = path[i], path[i + 1]
    local dx, dy = b.x - a.x, b.y - a.y
    local seg = math.sqrt(dx * dx + dy * dy)
    if s <= seg or i == #path - 1 then
      local t = seg > 0 and math.min(1, s / seg) or 0
      return a.x + dx * t, a.y + dy * t, atan2(dy, dx)
    end
    s = s - seg
  end
end

local function place(c)
  -- пути по всем оставшимся участкам: от пункта позади головы до конца маршрута
  local first = nil
  for i = 1, #c.places - 1 do
    local p = roadPath(c.places[i], c.places[i + 1])
    if p then
      REDFRONT_ROADS[c.places[i].id .. ">" .. c.places[i + 1].id] = p
      if i == 1 then first = p end
    end
  end
  if not first then return false, "дорога для участка с головой колонны не найдена" end
  local sHead = projectS(first, c.head.x, c.head.y)
  local units = {}
  for k, u in ipairs(c.units) do
    local x, y, hdg = pointAt(first, sHead - (u.off or (k - 1) * c.spacing))   -- off: смещение машины от головы, м (разрывы в колонне сохраняются)
    units[#units + 1] = { name = u.name, type = u.type, x = x, y = y, heading = hdg, skill = "High", playerCanDrive = false }
  end
  local hx, hy = pointAt(first, sHead)
  local points = { { x = hx, y = hy, action = "On Road", type = "Turning Point", speed = c.speed, ETA = 0, ETA_locked = false, speed_locked = true } }
  for _, w in ipairs(c.route) do
    points[#points + 1] = { x = w.x, y = w.y, action = "On Road", type = "Turning Point", speed = c.speed, ETA = 0, ETA_locked = false, speed_locked = true }
  end
  local data = { name = c.name, groupId = c.groupId, task = "Ground Nothing", units = units, route = { points = points } }
  coalition.addGroup(c.country, Group.Category.GROUND, data)
  -- опции группы из .miz при пересоздании теряются: ставим заново (сразу и через секунду - контроллер может быть ещё не готов)
  local function applyOptions()
    local grp = Group.getByName(c.name)
    if not grp then return end
    local ctl = grp:getController()
    for _, o in ipairs(c.options or {}) do pcall(function() ctl:setOption(o[1], o[2]) end) end
  end
  if c.options and #c.options > 0 then
    pcall(applyOptions)
    timer.scheduleFunction(function() pcall(applyOptions); return nil end, nil, timer.getTime() + 1)
  end
  return true, string.format("на дороге: %d машин", #units)
end

for _, c in ipairs(COLUMNS) do
  local ok, res, msg = pcall(place, c)          -- ok=false - ошибка Lua; res=false - дорога не найдена (msg - почему)
  if not ok then msg = "ошибка: " .. tostring(res) end
  REDFRONT_COLUMN_LOG[c.name] = msg
  env.info("redfront column " .. c.name .. ": " .. tostring(msg))
end
