-- redfront lz | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Площадки для вертолётов (общий модуль для csar.lua и assault.lua; исполняется первым).
-- Генератор (pydcs) местности не знает: пилот на земле и площадка десанта стоят в расчётной точке - в лесу, в
-- посёлке, у воды. В начале миссии точка переносится на ближайшую открытую площадку: суша (не вода, не ВПП), без
-- строений и объектов карты ближе clear_r, перепад высот не больше max_slope на slope_step - кольцами шагом ring_step
-- до max_r. Вертолётам ИИ, которые туда летят, маршрут пересчитывается: подход, посадка (Land) на новой точке,
-- возврат на свой аэродром.
REDFRONT_LZ = REDFRONT_LZ or {}
local CFG = { clear_r = 45, slope_step = 20, max_slope = 4, ring_step = 60, max_r = 1500, bearings = 12 }
REDFRONT_LZ.CFG = CFG

local function h(x, y) return land.getHeight({ x = x, y = y }) end

local function open(x, y)
  local s = land.getSurfaceType({ x = x, y = y })
  if s ~= land.SurfaceType.LAND and s ~= land.SurfaceType.ROAD then return false end
  local h0, d = h(x, y), CFG.slope_step
  for _, o in ipairs({ { d, 0 }, { -d, 0 }, { 0, d }, { 0, -d } }) do
    if math.abs(h(x + o[1], y + o[2]) - h0) > CFG.max_slope then return false end
    local so = land.getSurfaceType({ x = x + o[1], y = y + o[2] })
    if so ~= land.SurfaceType.LAND and so ~= land.SurfaceType.ROAD then return false end
  end
  local n = 0
  local vol = { id = world.VolumeType.SPHERE, params = { point = { x = x, y = h0, z = y }, radius = CFG.clear_r } }
  pcall(function() world.searchObjects(Object.Category.SCENERY, vol, function() n = n + 1; return n < 1 end) end)
  return n == 0
end
REDFRONT_LZ.open = open

-- Ближайшая открытая точка к (x, y) (x - север, y - восток, как в .miz); не нашлось - исходная.
function REDFRONT_LZ.find(x, y, max_r)
  if open(x, y) then return x, y, 0 end
  for r = CFG.ring_step, max_r or CFG.max_r, CFG.ring_step do
    local n = math.max(CFG.bearings, math.floor(2 * math.pi * r / CFG.ring_step))
    for i = 0, n - 1 do
      local a = 2 * math.pi * i / n
      local px, py = x + r * math.cos(a), y + r * math.sin(a)
      if open(px, py) then return px, py, r end
    end
  end
  return x, y, -1
end

-- Вертолёты ИИ группы - на новую площадку: подход, посадка на land_s, возврат на аэродром airdromeId.
function REDFRONT_LZ.retask(groupName, x, y, land_s, airdromeId, alt, speed)
  local g = Group.getByName(groupName)
  if not g or not g:getUnit(1) then return false end
  for _, u in ipairs(g:getUnits()) do
    if u.getPlayerName and u:getPlayerName() then return false end   -- игрок летит сам
  end
  local p = g:getUnit(1):getPoint()
  local pts = {
    { x = p.x, y = p.z, alt = alt or 50, alt_type = "RADIO", type = "Turning Point", action = "Turning Point", speed = speed or 55 },
    { x = x, y = y, alt = alt or 50, alt_type = "RADIO", type = "Turning Point", action = "Turning Point", speed = speed or 55,
      task = { id = "ComboTask", params = { tasks = { { number = 1, auto = false, enabled = true, id = "Land",
        params = { x = x, y = y, duration = land_s or 90, durationFlag = true } } } } } },
  }
  if airdromeId then
    local ab
    for _, b in ipairs(world.getAirbases() or {}) do
      if b:getID() == airdromeId then ab = b end
    end
    if ab then
      local bp = ab:getPoint()
      pts[#pts + 1] = { x = bp.x, y = bp.z, alt = 0, alt_type = "RADIO", type = "Land", action = "Landing",
                        airdromeId = airdromeId, speed = speed or 55 }
    end
  end
  g:getController():setTask({ id = "Mission", params = { route = { points = pts } } })
  return true
end
