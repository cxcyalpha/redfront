-- redfront debrief hook | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Пишет результаты вылета в <Saved Games>\DCS...\redfront\debrief_@CAMPAIGN@_@SORTIE@.json:
-- каждые 30 с, на каждой потере/посадке и по окончании миссии.
-- ТРЕБУЕТ: io и lfs не "санитизированы" в <DCS>\Scripts\MissionScripting.lua.
-- Подход (хук в миссии + JSON + чтение приложением) взят из SQE (MIT, MarkuzJuniuz); код написан заново.
if not (io and lfs) then
  env.warning("redfront: io/lfs sanitized - results cannot be saved (patch Scripts/MissionScripting.lua)")
  trigger.action.outText("redfront: результаты не сохранятся - MissionScripting.lua не разблокирован", 30)
  return
end
local DIR = lfs.writedir() .. "redfront"
lfs.mkdir(DIR)
local OUT = DIR .. "\\debrief_@CAMPAIGN@_@SORTIE@.json"
local TRACK = { @TRACK@ }        -- наземные юниты, пересоздаваемые скриптами при старте (колонна, части в бою); позиции пишем
local dead, ejected, landed, takeoff = {}, {}, {}, {}
local ended = false

local function esc(s)
  return (tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", string.byte(c)) end))
end
local function keys(t)
  local o = {}
  for k, _ in pairs(t) do o[#o + 1] = '"' .. esc(k) .. '"' end
  table.sort(o)
  return "[" .. table.concat(o, ",") .. "]"
end
local TRACKED = {}
for _, n in ipairs(TRACK) do TRACKED[n] = true end
-- пути по дорогам, найденные скриптом колонны (column_road.lua): модель запомнит их после дебрифа
local function roads()
  if type(REDFRONT_ROADS) ~= "table" then return "{}" end
  local o = {}
  for id, path in pairs(REDFRONT_ROADS) do
    local pts = {}
    for _, p in ipairs(path) do pts[#pts + 1] = string.format("[%.1f,%.1f]", p.x, p.y) end
    o[#o + 1] = string.format('"%s":[%s]', esc(id), table.concat(pts, ","))
  end
  return "{" .. table.concat(o, ",") .. "}"
end
local function columnLog()
  if type(REDFRONT_COLUMN_LOG) ~= "table" then return "{}" end
  local o = {}
  for k, v in pairs(REDFRONT_COLUMN_LOG) do o[#o + 1] = string.format('"%s":"%s"', esc(k), esc(v)) end
  return "{" .. table.concat(o, ",") .. "}"
end
-- место боя, выбранное battle_site.lua (сдвиг, м): модель запомнит его после дебрифа
local function sites()
  if type(REDFRONT_SITES) ~= "table" then return "{}" end
  local o = {}
  for k, v in pairs(REDFRONT_SITES) do o[#o + 1] = string.format('"%s":[%.1f,%.1f]', esc(k), v.x, v.y) end
  return "{" .. table.concat(o, ",") .. "}"
end
local function siteLog()
  if type(REDFRONT_SITE_LOG) ~= "table" then return "{}" end
  local o = {}
  for k, v in pairs(REDFRONT_SITE_LOG) do o[#o + 1] = string.format('"%s":"%s"', esc(k), esc(v)) end
  return "{" .. table.concat(o, ",") .. "}"
end
local targetDead = {}
-- цели в тылу: сколько объектов карты в районе и сколько из них разрушено
local function targets()
  if type(REDFRONT_TARGETS) ~= "table" then return "{}" end
  local dead_by = {}
  for _, id in pairs(targetDead) do dead_by[id] = (dead_by[id] or 0) + 1 end
  local o = {}
  for id, t in pairs(REDFRONT_TARGETS) do o[#o + 1] = string.format('"%s":[%d,%d]', esc(id), t.n or 0, dead_by[id] or 0) end
  return "{" .. table.concat(o, ",") .. "}"
end
-- вертолётный десант (assault.lua): сколько бортов село на площадку из скольких
local function assault()
  if type(REDFRONT_ASSAULT) ~= "table" then return "{}" end
  local o = {}
  for id, a in pairs(REDFRONT_ASSAULT) do o[#o + 1] = string.format('"%s":[%d,%d]', esc(id), a.landed or 0, a.total or 0) end
  return "{" .. table.concat(o, ",") .. "}"
end
local function positions()
  local o = {}
  for _, n in ipairs(TRACK) do
    if not dead[n] then
      local u = Unit.getByName(n)
      if u then
        local ok, p = pcall(function() return u:getPoint() end)
        if ok and p then o[#o + 1] = string.format('"%s":[%.1f,%.1f]', esc(n), p.x, p.z) end
      end
    end
  end
  return "{" .. table.concat(o, ",") .. "}"
end
local function dump()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write(string.format(
    '{"campaign":"@CAMPAIGN@","sortie":@SORTIE@,"mission_ended":%s,"time":%d,"dead":%s,"ejected":%s,"landed":%s,"takeoff":%s,"positions":%s,"roads":%s,"column_log":%s,"sites":%s,"site_log":%s,"targets":%s,"assault":%s}',
    tostring(ended), math.floor(timer.getTime()), keys(dead), keys(ejected), keys(landed), keys(takeoff), positions(), roads(), columnLog(), sites(), siteLog(), targets(), assault()))
  f:close()
end
local function nameOf(obj)
  if obj and obj.getName then
    local ok, n = pcall(function() return obj:getName() end)
    if ok and n ~= nil then return tostring(n) end   -- у объектов карты имя - число: везде как строка (targets.lua)
  end
end
-- Объекты карты (дома, деревья, мосты) тоже приходят в S_EVENT_DEAD, с числовыми именами: в посёлке их сотни.
-- Пишем только юниты и статику. Если категорию узнать нельзя (старый API) - пишем, как раньше.
local function isTracked(obj)
  if not (Object and Object.Category and obj and obj.getCategory) then return true end
  local ok, cat = pcall(function() return obj:getCategory() end)
  if not ok or cat == nil then return true end
  return cat == Object.Category.UNIT or cat == Object.Category.STATIC
end
local LOST = { [world.event.S_EVENT_DEAD] = true, [world.event.S_EVENT_CRASH] = true, [world.event.S_EVENT_PILOT_DEAD] = true }
if world.event.S_EVENT_UNIT_LOST then LOST[world.event.S_EVENT_UNIT_LOST] = true end

local H = {}
function H:onEvent(e)
  local n = nameOf(e.initiator)
  if not n then
    if e.id == world.event.S_EVENT_MISSION_END then ended = true; dump() end
    return
  end
  if LOST[e.id] then
    -- машины колонны, заменённые при перекладке на дорогу (column_road.lua), - не потери
    local respawning = TRACKED[n] and REDFRONT_RESPAWN_UNTIL and timer.getTime() < REDFRONT_RESPAWN_UNTIL
    if REDFRONT_TARGET_OF and REDFRONT_TARGET_OF[n] then           -- объект карты - часть цели в тылу (targets.lua)
      targetDead[n] = REDFRONT_TARGET_OF[n]; dump()
    elseif isTracked(e.initiator) and not landed[n] and not respawning then dead[n] = true; dump() end
  elseif e.id == world.event.S_EVENT_EJECTION then
    ejected[n] = true; dump()
  elseif e.id == world.event.S_EVENT_TAKEOFF then
    takeoff[n] = true; landed[n] = nil; dump()
  elseif e.id == world.event.S_EVENT_LAND then
    if not dead[n] then landed[n] = true; dump() end
  elseif e.id == world.event.S_EVENT_MISSION_END then
    ended = true; dump()
  end
end
world.addEventHandler(H)
timer.scheduleFunction(function(_, t) dump(); return t + 30 end, nil, timer.getTime() + 30)
dump()
