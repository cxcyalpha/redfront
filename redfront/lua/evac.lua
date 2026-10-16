-- redfront evac | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Эвакуация десанта (нужен lz.lua - исполняется раньше; игроку - ctld_cfg.lua).
--   * площадка: в начале миссии - на ближайшее открытое место (REDFRONT_LZ.find); рота (группы по вместимости
--     борта, имена фигур - из модели) пересоздаётся у неё; вертолётам ИИ маршрут пересчитывается на неё;
--   * борт ИИ, севший ближе r к площадке, забирает одну группу роты (она исчезает - "на борту");
--   * игрок - меню CTLD (Unload / Extract Troops): CTLD сообщает, какую группу забрал (REDFRONT_EVAC_CTLD);
--   * борт сбит - его группа погибла; фигуры, убитые на площадке, - тоже не вывезены.
-- REDFRONT_EVAC[id] = { saved, total, dead, player } - сколько фигур вывезено из бывших на площадке, из них игроком
-- (модель: итог игрока - его вывезенные, доля ведомых ИИ - по модели: не сбит огнём - вывез свою долю).
REDFRONT_EVAC = REDFRONT_EVAC or {}
local CHECK_S = 3
local SPECS = { @SPECS@ }   -- { id, title, side, country, x, y, r, land, home, helos = {...}, groups = {...}, troops = {{group, units = {{name, type}}}} }

local function dist(x1, y1, x2, y2) local dx, dy = x1 - x2, y1 - y2; return math.sqrt(dx * dx + dy * dy) end
local aboard = {}          -- борт -> { id, n } (сколько фигур на борту)
local figure = {}          -- имя фигуры -> id эвакуации (убита на площадке - dead)
local boarded = {}         -- группа роты уже на борту

local function count(s)
  local n = 0
  for _, t in ipairs(s.troops) do n = n + #t.units end
  return n
end

for _, s in ipairs(SPECS) do
  local nx, ny, moved = s.x, s.y, 0
  if REDFRONT_LZ and REDFRONT_LZ.find then nx, ny, moved = REDFRONT_LZ.find(s.x, s.y) end
  s.moved = moved
  if moved ~= 0 then                         -- рота - к перенесённой площадке (те же имена фигур)
    for _, t in ipairs(s.troops) do
      local g = Group.getByName(t.group)
      if g then g:destroy() end
      local units = {}
      for k, u in ipairs(t.units) do
        local a = 2 * math.pi * k / math.max(1, #t.units)
        units[#units + 1] = { name = u[1], type = u[2], x = nx + 40 * math.cos(a), y = ny + 40 * math.sin(a),
                              heading = a, skill = "Excellent", playerCanDrive = false }
      end
      coalition.addGroup(s.country, Group.Category.GROUND, { name = t.group, task = {}, units = units })
    end
  end
  s.x, s.y = nx, ny
  for _, t in ipairs(s.troops) do for _, u in ipairs(t.units) do figure[u[1]] = s.id end end
  REDFRONT_EVAC[s.id] = { saved = 0, total = count(s), dead = 0, player = 0 }
end

local function specOf(heli)
  for _, s in ipairs(SPECS) do
    for _, n in ipairs(s.helos) do if n == heli then return s end end
  end
end

local function board(s, heli, n, gname, player)
  if gname then boarded[gname] = true end
  aboard[heli] = { id = s.id, n = (aboard[heli] and aboard[heli].n or 0) + n, player = player }
  REDFRONT_EVAC[s.id].saved = REDFRONT_EVAC[s.id].saved + n
  if player then REDFRONT_EVAC[s.id].player = REDFRONT_EVAC[s.id].player + n end
end

-- игрок: CTLD забрал группу роты (ctld_cfg.lua, событие extract_troops)
function REDFRONT_EVAC_CTLD(heli, extracted)
  local s = specOf(heli)
  if not s or not extracted or not extracted.details then return end
  local gname = extracted.details.groupName
  for _, t in ipairs(s.troops) do
    if t.group == gname and not boarded[gname] then
      board(s, heli, #(extracted.details.units or {}), gname, true)
      trigger.action.outTextForCoalition(s.side, "Эвакуация: группа на борту (" .. s.title .. ")", 10)
      return
    end
  end
end

local retasked = {}
local function check()
  for _, s in ipairs(SPECS) do
    for _, gname in ipairs(s.groups) do                      -- ИИ - на перенесённую площадку, когда в воздухе
      if not retasked[gname] and REDFRONT_LZ and REDFRONT_LZ.retask then
        local g = Group.getByName(gname)
        local u = g and g:getUnit(1)
        if u and u:isExist() and u:inAir() then
          retasked[gname] = true
          if s.moved ~= 0 then REDFRONT_LZ.retask(gname, s.x, s.y, s.land, s.home) end
        end
      end
    end
    for _, n in ipairs(s.helos) do                           -- борт ИИ сел у площадки - забирает одну группу роты
      local u = Unit.getByName(n)
      if u and u:isExist() and not (u.getPlayerName and u:getPlayerName()) and not u:inAir() and not aboard[n] then
        local p = u:getPoint()
        if dist(p.x, p.z, s.x, s.y) <= s.r then
          for _, t in ipairs(s.troops) do
            local g = not boarded[t.group] and Group.getByName(t.group)
            if g and g:isExist() then
              local alive = 0
              for _, gu in ipairs(g:getUnits() or {}) do if gu and gu:isExist() then alive = alive + 1 end end
              board(s, n, alive, t.group)
              g:destroy()
              trigger.action.outTextForCoalition(s.side, "Эвакуация: группа на борту (" .. s.title .. ")", 10)
              break
            end
          end
          if not aboard[n] then aboard[n] = { id = s.id, n = 0 } end   -- забирать больше некого
        end
      end
    end
  end
  return timer.getTime() + CHECK_S
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)

local H = {}
function H:onEvent(e)
  if not e.initiator or not e.initiator.getName then return end
  local ok, name = pcall(function() return e.initiator:getName() end)
  if not ok then return end
  local lost = e.id == world.event.S_EVENT_DEAD or e.id == world.event.S_EVENT_CRASH or
               (world.event.S_EVENT_UNIT_LOST and e.id == world.event.S_EVENT_UNIT_LOST)
  if not lost then return end
  local a = aboard[name]
  if a and a.n > 0 then                                      -- борт сбит - его группа погибла
    REDFRONT_EVAC[a.id].saved = math.max(0, REDFRONT_EVAC[a.id].saved - a.n)
    if a.player then REDFRONT_EVAC[a.id].player = math.max(0, REDFRONT_EVAC[a.id].player - a.n) end
    aboard[name] = { id = a.id, n = 0 }
  elseif figure[name] then                                   -- фигура убита на площадке
    REDFRONT_EVAC[figure[name]].dead = REDFRONT_EVAC[figure[name]].dead + 1
    figure[name] = nil
  end
end
world.addEventHandler(H)
