-- redfront battle site | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Расстановка частей в бою по местности. Генератор (pydcs) рельефа не знает: боевые порядки он ставит по геометрии.
-- В начале миссии этот скрипт:
--   1. место боя: сдвигает весь бой целиком (обе стороны, взаимное расположение сохраняется) по сетке в пределах
--      search_r от расчётного - туда, где под позициями меньше воды, склонов и застройки и больше дорог и поля;
--      если место уже выбрано в прошлых вылетах (модель его помнит), search_r = 0;
--   2. каждая машина - в лучшую точку рядом со своей (до snap_r): дорога > у дороги > поле > застройка; вода и склон
--      исключены; не ближе min_gap к соседней;
--   3. взводы пересоздаются (coalition.addGroup) с теми же именами, groupId и машинами; опции ставятся заново.
-- Выбранный сдвиг пишется в REDFRONT_SITES - хук кладёт его в файл дебрифа, модель запоминает место боя.
-- Лес скрипту DCS не отдаёт (только тип поверхности и объекты карты) - от леса не уводим. Все веса - ОЦЕНКИ (build.py, SITE_CFG).

REDFRONT_SITES = REDFRONT_SITES or {}
REDFRONT_SITE_LOG = REDFRONT_SITE_LOG or {}
REDFRONT_RESPAWN_UNTIL = math.max(REDFRONT_RESPAWN_UNTIL or 0, timer.getTime() + 5)

local CFG = @CFG@
local BATTLES = { @BATTLES@ }
local ADS = { @ADS@ }          -- ПВО на позициях: каждая машина - на открытое место (follow - сдвигается с местом боя)
local SHIFT = {}               -- сдвиг места боя, найденный в этой миссии

local function xy(a, b)
  if type(a) == "table" then return a.x, a.y end
  return a, b
end

local function surface(x, y)
  return land.getSurfaceType({ x = x, y = y })
end

local function isWater(x, y)
  local s = surface(x, y)
  return s == land.SurfaceType.WATER or s == land.SurfaceType.SHALLOW_WATER
end

local function slope(x, y)              -- наибольший перепад высот на +-step, м
  local d, h0 = CFG.slope_step, land.getHeight({ x = x, y = y })
  local m = 0
  for _, o in ipairs({ { d, 0 }, { -d, 0 }, { 0, d }, { 0, -d } }) do
    m = math.max(m, math.abs(land.getHeight({ x = x + o[1], y = y + o[2] }) - h0))
  end
  return m
end

local function buildings(x, y, r)
  local n = 0
  local vol = { id = world.VolumeType.SPHERE, params = { point = { x = x, y = land.getHeight({ x = x, y = y }), z = y }, radius = r } }
  pcall(function() world.searchObjects(Object.Category.SCENERY, vol, function() n = n + 1; return true end) end)
  return n
end

local function roadDist(x, y)
  local ok, rx, ry = pcall(land.getClosestPointOnRoads, "roads", x, y)
  if not ok then return math.huge end
  rx, ry = xy(rx, ry)
  if not rx then return math.huge end
  return math.sqrt((rx - x) ^ 2 + (ry - y) ^ 2)
end

-- оценка точки; nil - нельзя (вода, склон)
local function score(x, y)
  if isWater(x, y) or slope(x, y) > CFG.max_slope then return nil end
  local s
  if surface(x, y) == land.SurfaceType.ROAD then s = CFG.w_road
  else
    local rd = roadDist(x, y)
    s = (rd <= CFG.near_road) and CFG.w_near_road or CFG.w_field
  end
  return s - CFG.w_building * math.min(CFG.building_cap, buildings(x, y, CFG.building_r))
end

local function siteScore(b, dx, dy)
  local total, n = 0, 0
  for _, p in ipairs(b.platoons) do
    for k, u in ipairs(p.units) do
      if k % CFG.sample == 1 or CFG.sample == 1 then
        local s = score(u.x + dx, u.y + dy)
        total = total + (s or CFG.w_reject)
        n = n + 1
      end
    end
  end
  return total / math.max(1, n) - CFG.w_distance * math.sqrt(dx * dx + dy * dy) / 1000
end

local function place(b)
  -- 1. место боя
  local bx, by, best = 0, 0, siteScore(b, 0, 0)
  local steps = math.floor(b.search_r / CFG.site_step)
  for i = -steps, steps do
    for j = -steps, steps do
      local dx, dy = i * CFG.site_step, j * CFG.site_step
      if (i ~= 0 or j ~= 0) and dx * dx + dy * dy <= b.search_r ^ 2 then
        local s = siteScore(b, dx, dy)
        if s > best then bx, by, best = dx, dy, s end
      end
    end
  end
  REDFRONT_SITES[b.key] = { x = b.shift.x + bx, y = b.shift.y + by }
  SHIFT[b.key] = { x = bx, y = by }
  -- 2. каждая машина - в лучшую точку рядом
  local placed = {}
  local function free(x, y)
    for _, q in ipairs(placed) do if (q.x - x) ^ 2 + (q.y - y) ^ 2 < CFG.min_gap ^ 2 then return false end end
    return true
  end
  local moved, rejected = 0, 0
  for _, p in ipairs(b.platoons) do
    p.new = {}
    for _, u in ipairs(p.units) do
      local x0, y0 = u.x + bx, u.y + by
      local bestS, px, py = nil, x0, y0
      for _, r in ipairs(CFG.snap_rings) do
        for k = 0, (r == 0 and 0 or CFG.snap_dirs - 1) do
          local a = 2 * math.pi * k / CFG.snap_dirs
          local x, y = x0 + r * math.cos(a), y0 + r * math.sin(a)
          if free(x, y) then
            local s = score(x, y)
            if s then
              s = s - CFG.w_snap * r / 100
              if bestS == nil or s > bestS then bestS, px, py = s, x, y end
            end
          end
        end
      end
      if bestS == nil then rejected = rejected + 1 end
      if px ~= x0 or py ~= y0 then moved = moved + 1 end
      placed[#placed + 1] = { x = px, y = py }
      p.new[#p.new + 1] = { name = u.name, type = u.type, x = px, y = py, heading = u.heading, skill = "High", playerCanDrive = false }
    end
  end
  -- 3. пересоздать взводы
  for _, p in ipairs(b.platoons) do
    local cx, cy = 0, 0
    for _, u in ipairs(p.new) do cx = cx + u.x; cy = cy + u.y end
    cx, cy = cx / #p.new, cy / #p.new
    local pts = { { x = cx, y = cy, action = "Off Road", type = "Turning Point", speed = p.speed, ETA = 0, ETA_locked = false, speed_locked = true } }
    for _, w in ipairs(p.route) do
      pts[#pts + 1] = { x = w.x + bx, y = w.y + by, action = "Rank", type = "Turning Point", speed = p.speed, ETA = 0, ETA_locked = false, speed_locked = true }
    end
    coalition.addGroup(p.country, Group.Category.GROUND, { name = p.name, groupId = p.groupId, task = "Ground Nothing", units = p.new, route = { points = pts } })
    local function opts()
      local g = Group.getByName(p.name)
      if not g then return end
      local c = g:getController()
      for _, o in ipairs(p.options) do pcall(function() c:setOption(o[1], o[2]) end) end
    end
    pcall(opts)
    timer.scheduleFunction(function() pcall(opts); return nil end, nil, timer.getTime() + 1)
  end
  return string.format("место боя сдвинуто на %.0f м (оценка %.2f), машин переставлено %d, без хорошего места %d",
                       math.sqrt(bx * bx + by * by), best, moved, rejected)
end

for _, b in ipairs(BATTLES) do
  local ok, msg = pcall(place, b)
  if not ok then msg = "ошибка: " .. tostring(msg) end
  REDFRONT_SITE_LOG[b.key] = msg
  env.info("redfront battle site " .. b.key .. ": " .. tostring(msg))
end

-- ВПП, рулёжка, стоянка (бетон аэродрома) ближе ad_runway_clear м - нельзя: ПВО не ставится на аэродром и под взлёт
local function nearRunway(x, y)
  if surface(x, y) == land.SurfaceType.RUNWAY then return true end
  for _, r in ipairs({ CFG.ad_runway_clear / 2, CFG.ad_runway_clear }) do
    for k = 0, 7 do
      local a = math.pi * k / 4
      if surface(x + r * math.cos(a), y + r * math.sin(a)) == land.SurfaceType.RUNWAY then return true end
    end
  end
  return false
end

-- ПВО: поле (можно у дороги), не на дороге, строения - большой минус; вода, склон и аэродром исключены
local function adScore(x, y)
  if isWater(x, y) or slope(x, y) > CFG.max_slope or nearRunway(x, y) then return nil end
  local s
  if surface(x, y) == land.SurfaceType.ROAD then s = CFG.ad_w_road
  else
    s = CFG.ad_w_field + ((roadDist(x, y) <= CFG.ad_near_road) and CFG.ad_w_near_road or 0)
  end
  return s - CFG.ad_w_building * buildings(x, y, CFG.ad_building_r)
end

-- позиция целиком: сколько машин нельзя поставить в точку со сдвигом (dx, dy) - вода, склон, аэродром, город
-- (строений ближе ad_town_r м - не меньше ad_town_n: из квартала машину за 400 м не вывести)
local function adBad(a, sx, sy)
  local n = 0
  for _, u in ipairs(a.units) do
    local x, y = u.x + sx, u.y + sy
    if adScore(x, y) == nil or buildings(x, y, CFG.ad_town_r) >= CFG.ad_town_n then n = n + 1 end
  end
  return n
end

local adPlaced = {}
local function placeAD(a)
  local sh = (a.follow and SHIFT[a.follow]) or { x = 0, y = 0 }
  local moved = 0
  local bad = adBad(a, sh.x, sh.y)
  if bad > 0 and not a.follow then            -- позиция на аэродроме, в воде, в городе: вся позиция - на ближнее место, где можно
    local best = { bad, 0, 0 }
    for _, r in ipairs(CFG.ad_site_rings) do
      for k = 0, CFG.ad_dirs - 1 do
        local ang = 2 * math.pi * k / CFG.ad_dirs
        local dx, dy = r * math.cos(ang), r * math.sin(ang)
        local b = adBad(a, sh.x + dx, sh.y + dy)
        if b < best[1] then best = { b, dx, dy } end
      end
      if best[1] == 0 then break end           -- ближнее кольцо, где можно всю позицию
    end
    sh = { x = sh.x + best[2], y = sh.y + best[3] }
    moved = math.sqrt(best[2] ^ 2 + best[3] ^ 2)
  end
  local new, inTown = {}, 0
  for _, u in ipairs(a.units) do
    local x0, y0 = u.x + sh.x, u.y + sh.y
    local bestS, px, py = nil, x0, y0
    for _, r in ipairs(CFG.ad_rings) do
      for k = 0, (r == 0 and 0 or CFG.ad_dirs - 1) do
        local ang = 2 * math.pi * k / CFG.ad_dirs
        local x, y = x0 + r * math.cos(ang), y0 + r * math.sin(ang)
        local ok = true
        for _, q in ipairs(adPlaced) do if (q.x - x) ^ 2 + (q.y - y) ^ 2 < CFG.ad_gap ^ 2 then ok = false; break end end
        if ok then
          local s = adScore(x, y)
          if s then
            s = s - CFG.w_snap * r / 100
            if bestS == nil or s > bestS then bestS, px, py = s, x, y end
          end
        end
      end
    end
    if buildings(px, py, CFG.ad_building_r) > 0 then inTown = inTown + 1 end
    adPlaced[#adPlaced + 1] = { x = px, y = py }
    new[#new + 1] = { name = u.name, type = u.type, x = px, y = py, heading = u.heading, skill = "High", playerCanDrive = false }
  end
  coalition.addGroup(a.country, Group.Category.GROUND, { name = a.name, groupId = a.groupId, task = "Ground Nothing", units = new,
    route = { points = { { x = new[1].x, y = new[1].y, action = "Off Road", type = "Turning Point", speed = 0, ETA = 0, ETA_locked = false, speed_locked = true } } } })
  return string.format("ПВО на открытом месте: %d машин, у строений осталось %d%s", #new, inTown,
                       moved > 0 and string.format(", позиция сдвинута на %.0f м (аэродром, вода, город)", moved) or "")
end

for _, a in ipairs(ADS) do
  local ok, msg = pcall(placeAD, a)
  if not ok then msg = "ошибка: " .. tostring(msg) end
  REDFRONT_SITE_LOG[a.name] = msg
  env.info("redfront battle site " .. a.name .. ": " .. tostring(msg))
end
