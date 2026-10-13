-- redfront map probe | sector @SECTOR@
-- Служебная миссия: проходит весь сектор сеткой и собирает объекты карты (как "Assign as..." в редакторе),
-- пишет их в <Saved Games>\DCS...\redfront\map_@SECTOR@.json. Летать не нужно: дождаться сообщения и выйти.
--   * мосты: все объекты карты с "bridge" в типе; для каждого - стоит ли он над водой (land.getSurfaceType);
--   * склады: все объекты карты, чей тип содержит ключевое слово складов (DEPOT_KEYS: silo, stock, ...);
--   * заводы: все объекты карты с ключевым словом заводов (FACTORY_KEYS: industrial);
--   * у пунктов известных складов - какие вообще типы объектов есть рядом (для дополнения ключевых слов).
-- Сектор большой: ячейки сетки обрабатываются по несколько за такт (timer), ход виден в сообщениях.
-- ТРЕБУЕТ: io и lfs не "санитизированы" в <DCS>\Scripts\MissionScripting.lua.
if not (io and lfs) then
  trigger.action.outText("redfront: объекты карты не сохранятся - MissionScripting.lua не разблокирован", 60)
  return
end
local DIR = lfs.writedir() .. "redfront"
lfs.mkdir(DIR)
local OUT = DIR .. "\\map_@SECTOR@.json"
local TILES = { @TILES@ }        -- центры ячеек сетки { x, y } в координатах карты DCS
local TILE_R = @TILE_R@          -- радиус поиска в ячейке, м
local PER_TICK = @PER_TICK@      -- ячеек за такт
local DEPOTS = { @DEPOTS@ }      -- { id, x, y, r } - перечень типов у пунктов известных складов
local DEPOT_KEYS = { @DEPOT_KEYS@ }
local FACTORY_KEYS = { @FACTORY_KEYS@ }

local function has(keys, tp)
  for _, k in ipairs(keys) do if string.find(tp, k, 1, true) then return true end end
  return false
end

local function esc(s)
  return (tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", string.byte(c)) end))
end

local function scan(x, y, r, fn)
  local vol = { id = world.VolumeType.SPHERE,
                params = { point = { x = x, y = land.getHeight({ x = x, y = y }), z = y }, radius = r } }
  world.searchObjects(Object.Category.SCENERY, vol, function(obj)
    pcall(function() fn(tostring(obj:getName()), obj:getTypeName() or "?", obj:getPoint()) end)
    return true
  end)
end

local function isWater(x, y)
  local s = land.getSurfaceType({ x = x, y = y })
  return s == land.SurfaceType.WATER or s == land.SurfaceType.SHALLOW_WATER
end

local seen, bridges, depotObjs, factoryObjs, errors = {}, {}, {}, {}, {}
local nBridges, nDepot, nFactory = 0, 0, 0

-- типы у пунктов известных складов
local depots = {}
for _, o in ipairs(DEPOTS) do
  local types = {}
  local ok, err = pcall(scan, o.x, o.y, o.r, function(name, tp, p)
    local t = types[tp] or { n = 0, x = 0, y = 0 }
    t.n, t.x, t.y = t.n + 1, t.x + p.x, t.y + p.z
    types[tp] = t
  end)
  if not ok then errors[#errors + 1] = string.format('"%s":"%s"', esc(o.id), esc(err)) end
  local list = {}
  for tp, t in pairs(types) do list[#list + 1] = string.format('"%s":[%d,%.1f,%.1f]', esc(tp), t.n, t.x / t.n, t.y / t.n) end
  depots[#depots + 1] = string.format('"%s":{%s}', esc(o.id), table.concat(list, ","))
end

local function finish()
  local f = io.open(OUT, "w")
  if not f then
    trigger.action.outText("redfront: не удалось открыть файл " .. OUT, 120)
    return
  end
  f:write(string.format('{"sector":"@SECTOR@","bridges_all":[%s],"depot_objects_all":[%s],"factory_objects_all":[%s],"depots":{%s},"errors":{%s}}',
    table.concat(bridges, ","), table.concat(depotObjs, ","), table.concat(factoryObjs, ","), table.concat(depots, ","), table.concat(errors, ",")))
  f:close()
  trigger.action.outText(string.format("redfront: объекты карты записаны (мостов %d, объектов складов %d, заводов %d, ошибок %d) в %s. Можно выходить.",
    nBridges, nDepot, nFactory, #errors, OUT), 300)
end

local i, lastPct = 0, -1
local function step()
  for _ = 1, PER_TICK do
    i = i + 1
    local t = TILES[i]
    if not t then
      finish()
      return nil
    end
    local ok, err = pcall(scan, t.x, t.y, TILE_R, function(name, tp, p)
      if seen[name] then return end
      local l = string.lower(tp)
      if string.find(l, "bridge", 1, true) then
        seen[name] = true
        nBridges = nBridges + 1
        bridges[#bridges + 1] = string.format('["%s","%s",%.1f,%.1f,%d]', esc(name), esc(tp), p.x, p.z, isWater(p.x, p.z) and 1 or 0)
      elseif has(DEPOT_KEYS, l) then
        seen[name] = true
        nDepot = nDepot + 1
        depotObjs[#depotObjs + 1] = string.format('["%s","%s",%.1f,%.1f]', esc(name), esc(tp), p.x, p.z)
      elseif has(FACTORY_KEYS, l) then
        seen[name] = true
        nFactory = nFactory + 1
        factoryObjs[#factoryObjs + 1] = string.format('["%s","%s",%.1f,%.1f]', esc(name), esc(tp), p.x, p.z)
      end
    end)
    if not ok and #errors < 20 then errors[#errors + 1] = string.format('"tile%d":"%s"', i, esc(err)) end
  end
  local pct = math.floor(100 * i / #TILES / 10) * 10
  if pct ~= lastPct then
    lastPct = pct
    trigger.action.outText(string.format("redfront: зонд карты %d%% (мостов %d, объектов складов %d, заводов %d)", pct, nBridges, nDepot, nFactory), 10, true)
  end
  return timer.getTime() + 0.05
end

trigger.action.outText(string.format("redfront: зонд карты - ячеек %d, ждите сообщения 'записаны'", #TILES), 10)
timer.scheduleFunction(step, nil, timer.getTime() + 1)
