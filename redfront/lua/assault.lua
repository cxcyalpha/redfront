-- redfront assault | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Вертолётный десант (нужен lz.lua - исполняется раньше).
--   * площадка: в начале миссии - на ближайшее открытое место (REDFRONT_LZ.find); вертолётам ИИ маршрут
--     пересчитывается на неё (когда взлетят);
--   * рота делится по бортам (доля каждого - свои фигуры); борт ИИ, севший ближе r к площадке, высаживает свою долю
--     сам; игрок - через меню F10 "Десант": "Загрузить десант" (на земле, у своего аэродрома), "Высадить десант"
--     (на земле, ближе r к площадке), "Площадка" (пеленг, дальность, дым);
--   * высаженные фигуры появляются у вертолёта (coalition.addGroup) с именами из модели - их потери пишет хук;
--   * если в миссии CTLD (ctld_cfg.lua: борт игрока в REDFRONT_CTLD.pilots) - погрузка и высадка игрока через меню CTLD
--     ("Перевозки (CTLD)" -> "Десант"), своего меню нет: группа, высаженная CTLD ближе r к площадке, заменяется долей
--     роты (REDFRONT_ASSAULT_CTLD); дальше - остаётся группой CTLD, её можно забрать обратно и высадить на площадке.
-- Сколько бортов высадили свою долю из скольких - REDFRONT_ASSAULT[id] (модель: assault.py).
REDFRONT_ASSAULT = REDFRONT_ASSAULT or {}
local CHECK_S = 3
local LOAD_R = 3000             -- загрузка у своего аэродрома: ближе стольких метров
local SPECS = { @SPECS@ }       -- { id, title, side, country, x, y, r, land, home, helos = {...}, groups = {...}, troops = {{name, type}} }

local function dist(x1, y1, x2, y2) local dx, dy = x1 - x2, y1 - y2; return math.sqrt(dx * dx + dy * dy) end
local function msg(u, text, t)
  local ok, g = pcall(function() return u:getGroup() end)
  if ok and g then trigger.action.outTextForGroup(g:getID(), text, t or 10) end
end
local function isPlayer(u) return u.getPlayerName and u:getPlayerName() ~= nil end

local function share(s, idx)    -- фигуры роты на борту idx (по кругу)
  local out = {}
  for i, t in ipairs(s.troops) do
    if (i - 1) % #s.helos == idx - 1 then out[#out + 1] = t end
  end
  return out
end

local function unload(s, st, name, u)
  local idx
  for i, n in ipairs(s.helos) do if n == name then idx = i end end
  if not idx or st.seen[name] then return end
  st.seen[name] = true
  st.landed = st.landed + 1
  local p = u:getPoint()
  local units = {}
  for k, t in ipairs(share(s, idx)) do
    local a = 2 * math.pi * k / 8
    units[#units + 1] = { name = t.name, type = t.type, x = p.x + 25 * math.cos(a) + 15, y = p.z + 25 * math.sin(a),
                          heading = a, skill = "Excellent", playerCanDrive = false }
  end
  if #units > 0 then
    coalition.addGroup(s.country, Group.Category.GROUND, { name = s.id .. " / " .. idx, task = {}, units = units })
  end
  if not st.out then
    st.out = true
    trigger.action.outTextForCoalition(s.side, "Десант высаживается: " .. s.title, 15)
  end
end

for _, s in ipairs(SPECS) do
  local nx, ny, moved = s.x, s.y, 0
  if REDFRONT_LZ and REDFRONT_LZ.find then nx, ny, moved = REDFRONT_LZ.find(s.x, s.y) end
  s.x, s.y = nx, ny
  s.moved = moved
  REDFRONT_ASSAULT[s.id] = { landed = 0, total = #s.helos, seen = {}, out = false }
end

local retasked = {}
local loaded = {}

local function check()
  for _, s in ipairs(SPECS) do
    local st = REDFRONT_ASSAULT[s.id]
    for _, gname in ipairs(s.groups) do                         -- ИИ - на перенесённую площадку, когда в воздухе
      if not retasked[gname] and REDFRONT_LZ and REDFRONT_LZ.retask then
        local g = Group.getByName(gname)
        local u = g and g:getUnit(1)
        if u and u:isExist() and u:inAir() then
          retasked[gname] = true
          if s.moved ~= 0 then REDFRONT_LZ.retask(gname, s.x, s.y, s.land, s.home) end
        end
      end
    end
    for _, n in ipairs(s.helos) do                              -- борт ИИ сел на площадку - высаживает свою долю
      local u = Unit.getByName(n)
      if u and u:isExist() and not isPlayer(u) and not u:inAir() and not st.seen[n] then
        local p = u:getPoint()
        if dist(p.x, p.z, s.x, s.y) <= s.r then unload(s, st, n, u) end
      end
    end
  end
  return timer.getTime() + CHECK_S
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)

local function specOf(name)
  for _, s in ipairs(SPECS) do
    for _, n in ipairs(s.helos) do if n == name then return s end end
  end
end

local function nearOwnBase(u)
  local p = u:getPoint()
  for _, b in ipairs(coalition.getAirbases(u:getCoalition()) or {}) do
    local bp = b:getPoint()
    if dist(p.x, p.z, bp.x, bp.z) <= LOAD_R then return true end
  end
  return false
end

local function cmdLoad(name)
  local u, s = Unit.getByName(name), specOf(name)
  if not u or not s then return end
  if u:inAir() then msg(u, "Загрузка - только на земле.", 8); return end
  if REDFRONT_ASSAULT[s.id].seen[name] then msg(u, "Ваша доля десанта уже высажена.", 8); return end
  if not nearOwnBase(u) then msg(u, "Загрузка - у своего аэродрома.", 8); return end
  loaded[name] = true
  local idx = 1
  for i, n in ipairs(s.helos) do if n == name then idx = i end end
  msg(u, "Десант на борту (" .. #share(s, idx) .. " фигур): " .. s.title .. ". Площадка - в меню.", 15)
end

local function cmdUnload(name)
  local u, s = Unit.getByName(name), specOf(name)
  if not u or not s then return end
  if not loaded[name] then msg(u, "Десанта на борту нет - сначала загрузите у своего аэродрома.", 10); return end
  if u:inAir() then msg(u, "Высадка - только на земле.", 8); return end
  local p = u:getPoint()
  local r = dist(p.x, p.z, s.x, s.y)
  if r > s.r then msg(u, string.format("Вы не на площадке: до неё %.1f км.", r / 1000), 10); return end
  loaded[name] = nil
  unload(s, REDFRONT_ASSAULT[s.id], name, u)
  msg(u, "Десант высажен. Возвращайтесь.", 15)
end

local function cmdInfo(name)
  local u, s = Unit.getByName(name), specOf(name)
  if not u or not s then return end
  local p = u:getPoint()
  local brg = math.deg(math.atan2(s.y - p.z, s.x - p.x)) % 360
  trigger.action.smoke({ x = s.x, y = land.getHeight({ x = s.x, y = s.y }), z = s.y }, s.side == 2 and 4 or 1)
  msg(u, string.format("Площадка: пеленг %03d, %.1f км (дым)%s.", brg, dist(p.x, p.z, s.x, s.y) / 1000,
      s.moved > 0 and string.format("; перенесена на открытое место (%.0f м)", s.moved) or ""), 15)
end

-- высадка игрока через CTLD (ctld_cfg.lua): grp - группа, которую создал CTLD
function REDFRONT_ASSAULT_CTLD(name, grp)
  local u, s = Unit.getByName(name), specOf(name)
  if not u or not s then return end
  local p = u:getPoint()
  local r = dist(p.x, p.z, s.x, s.y)
  if r > s.r then
    msg(u, string.format("Вы не на площадке (до неё %.1f км): высадка не засчитана. Заберите группу обратно (\"Высадить / забрать десант\") и высадите на площадке.", r / 1000), 20)
    return
  end
  if REDFRONT_ASSAULT[s.id].seen[name] then return end
  pcall(function() grp:destroy() end)                         -- вместо бойцов CTLD - доля роты из модели
  unload(s, REDFRONT_ASSAULT[s.id], name, u)
  msg(u, "Десант высажен на площадке. Возвращайтесь.", 15)
end

local menus = {}
local H = {}
function H:onEvent(e)
  if e.id ~= world.event.S_EVENT_BIRTH or not e.initiator or not e.initiator.getName then return end
  local u = e.initiator
  local ok, name = pcall(function() return u:getName() end)
  if not ok or not specOf(name) or not isPlayer(u) then return end
  if REDFRONT_CTLD and REDFRONT_CTLD.pilots[name] then return end   -- погрузка и высадка - меню CTLD
  local g = u:getGroup()
  if not g or menus[g:getID()] then return end
  menus[g:getID()] = true
  local gid = g:getID()
  local root = missionCommands.addSubMenuForGroup(gid, "Десант")
  missionCommands.addCommandForGroup(gid, "Загрузить десант", root, function() pcall(cmdLoad, name) end)
  missionCommands.addCommandForGroup(gid, "Высадить десант", root, function() pcall(cmdUnload, name) end)
  missionCommands.addCommandForGroup(gid, "Площадка", root, function() pcall(cmdInfo, name) end)
end
world.addEventHandler(H)
