-- redfront csar | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Поиск и спасение сбитых экипажей. Механика - по мотивам DCS-CSAR (ciribob, github.com/ciribob/DCS-CSAR): у него
-- нет лицензии, поэтому код свой и без MIST.
--   * экипажи на земле из модели (стоят в .miz) и новые - катапультировавшиеся в этой миссии (появляются у точки
--     катапультирования): бессмертны и невидимы для ИИ (их судьбу - плен - решает модель), огонь не ведут; в начале
--     миссии (новые - сразу) переносятся на ближайшую открытую площадку (lz.lua), вертолётам ИИ, летящим за ними,
--     маршрут пересчитывается на неё;
--   * у каждого - маяк ADF (AM, кГц) - звук маяка в .miz (trigger.action.radioTransmission);
--   * вертолёт своей стороны ближе near_r - "слышу вас"; сел ближе pickup_r - пилот бежит к нему и садится
--     (run_mps); завис ближе winch_r и ниже winch_h над ним на winch_s секунд - поднят лебёдкой;
--   * посадка с ним на свой аэродром - спасён; вертолёт сбит с ним на борту - погиб;
--   * меню F10 "CSAR" у вертолётов игроков: список экипажей (пеленг, дальность, частота), ракета, дым у ближнего.
-- Итог - REDFRONT_CSAR (rescued / lost по id), хук дебрифа пишет его в файл; модель - csar.py.
REDFRONT_CSAR = REDFRONT_CSAR or { rescued = {}, lost = {} }
local CFG = { sound = "l10n/DEFAULT/@SOUND@", near_r = 3000, pickup_r = 300, run_mps = 3, winch_r = 8, winch_h = 20,
              winch_s = 10, tick = 1 }
local DOWNED = { @DOWNED@ }       -- { id, group, side, title, freq } - экипажи из модели
local RESCUERS = { @RESCUERS@ }   -- { group, downed, home, land } - вертолёты ИИ, летящие за экипажем
local SPAWN = { [1] = { country = @RED_COUNTRY@, type = "Infantry AK" }, [2] = { country = @BLUE_COUNTRY@, type = "Soldier M4" } }
local OWN_BASES = { [1] = { @RED_BASES@ }, [2] = { @BLUE_BASES@ } }   -- аэродромы сторон (имя DCS -> true)
local CAPACITY = { ["Mi-8MT"] = 16, ["UH-1H"] = 8, ["UH-60A"] = 8, ["CH-47D"] = 20, ["CH-53E"] = 20, ["Mi-26"] = 40,
                   ["Mi-24P"] = 4, ["SA342M"] = 1 }

local active, onboard, seen, run, hover, menus = {}, {}, {}, {}, {}, {}
local freqNext = 1190             -- новые катапультировавшиеся - сверху диапазона (модель раздаёт снизу, от 200)
local seq = 0

local function dist(a, b) local dx, dz = a.x - b.x, a.z - b.z; return math.sqrt(dx * dx + dz * dz) end
local function msg(u, text, t)
  local ok, g = pcall(function() return u:getGroup() end)
  if ok and g then trigger.action.outTextForGroup(g:getID(), text, t or 10) end
end
local function nOnboard(name) local n = 0; for _ in pairs(onboard[name] or {}) do n = n + 1 end; return n end

local function relocate(d)          -- пилот - на ближайшую открытую площадку (lz.lua): туда сможет сесть вертолёт
  local g = Group.getByName(d.group)
  local u = g and g:getUnit(1)
  if not u or not (REDFRONT_LZ and REDFRONT_LZ.find) then return end
  local p = u:getPoint()
  local x, y, moved = REDFRONT_LZ.find(p.x, p.z, 800)
  if moved > 0 then                 -- группа с тем же именем заменяется (coalition.addGroup)
    coalition.addGroup(SPAWN[d.side].country, Group.Category.GROUND, { name = d.group, task = {}, units = {
      { name = u:getName(), type = u:getTypeName(), x = x, y = y, heading = 0, skill = "Excellent", playerCanDrive = false } } })
  end
end

local function setup(d)
  local g = Group.getByName(d.group)
  if not g then return end
  local c = g:getController()
  c:setCommand({ id = "SetImmortal", params = { value = true } })
  c:setCommand({ id = "SetInvisible", params = { value = true } })
  c:setOption(AI.Option.Ground.id.ROE, AI.Option.Ground.val.ROE.WEAPON_HOLD)
  local u = g:getUnit(1)
  if u then
    trigger.action.radioTransmission(CFG.sound, u:getPoint(), 0, true, d.freq * 1000, 1000, "csar_" .. d.id)
  end
  active[d.id] = d
end
for _, d in ipairs(DOWNED) do pcall(relocate, d); pcall(setup, d) end

local function helis(side)
  local out = {}
  for _, g in ipairs(coalition.getGroups(side, Group.Category.HELICOPTER) or {}) do
    for _, u in ipairs(g:getUnits() or {}) do
      if u and u:isExist() and u:isActive() then out[#out + 1] = u end
    end
  end
  return out
end

local function runTo(d, h)
  local g = Group.getByName(d.group)
  if not g then return end
  local p, hp = g:getUnit(1):getPoint(), h:getPoint()
  g:getController():setTask({ id = "Mission", params = { route = { points = {
    { x = p.x, y = p.z, action = "Off Road", speed = CFG.run_mps, type = "Turning Point" },
    { x = hp.x, y = hp.z, action = "Off Road", speed = CFG.run_mps, type = "Turning Point" } } } } })
end

local function pickup(h, d)
  local g = Group.getByName(d.group)
  if g then g:destroy() end
  trigger.action.stopRadioTransmission("csar_" .. d.id)
  onboard[h:getName()] = onboard[h:getName()] or {}
  onboard[h:getName()][d.id] = true
  active[d.id] = nil
  msg(h, d.title .. " на борту. Доставьте на свой аэродром.", 15)
end

local retasked = {}
local function tick()
  for _, rs in ipairs(RESCUERS) do      -- вертолёты ИИ - на площадку у пилота (когда взлетят)
    local d = active[rs.downed]
    local g = Group.getByName(rs.group)
    local hu = g and g:getUnit(1)
    if not retasked[rs.group] and d and hu and hu:isExist() and hu:inAir() and REDFRONT_LZ and REDFRONT_LZ.retask then
      local pg = Group.getByName(d.group)
      local pu = pg and pg:getUnit(1)
      if pu then
        local pp = pu:getPoint()
        local x, y = REDFRONT_LZ.find(pp.x + 40, pp.z, 300)
        retasked[rs.group] = true
        REDFRONT_LZ.retask(rs.group, x, y, rs.land, rs.home)
      end
    end
  end
  for id, d in pairs(active) do
    local g = Group.getByName(d.group)
    local pu = g and g:getUnit(1)
    if pu then
      local pp = pu:getPoint()
      for _, h in ipairs(helis(d.side)) do
        local hp = h:getPoint()
        local r = dist(hp, pp)
        local key = h:getName() .. "|" .. id
        if r < CFG.near_r then
          if not seen[key] then
            seen[key] = true
            msg(h, d.title .. ": слышу вас! Ракета и дым - в меню F10, CSAR. Садитесь рядом или зависните надо мной.", 15)
          end
          if nOnboard(h:getName()) < (CAPACITY[h:getTypeName()] or 4) then
            if not h:inAir() and r <= CFG.pickup_r then            -- сел рядом: пилот бежит к вертолёту
              if not run[key] then
                run[key] = math.ceil(r / CFG.run_mps)
                runTo(d, h)
                msg(h, d.title .. ": бегу к вам, " .. run[key] .. " с.", 10)
              else
                run[key] = run[key] - CFG.tick
              end
              if run[key] <= 0 then run[key] = nil; pickup(h, d); break end
            else
              run[key] = nil
            end
            if h:inAir() and r <= CFG.winch_r and hp.y - pp.y <= CFG.winch_h then   -- зависание: лебёдка
              hover[key] = (hover[key] or CFG.winch_s) - CFG.tick
              msg(h, "Лебёдка: держите зависание ещё " .. hover[key] .. " с.", 2)
              if hover[key] <= 0 then hover[key] = nil; pickup(h, d); break end
            else
              hover[key] = nil
            end
          end
        end
      end
    end
  end
  return timer.getTime() + CFG.tick
end
timer.scheduleFunction(tick, nil, timer.getTime() + CFG.tick)

local function nearest(h)
  local best, br
  for _, d in pairs(active) do
    local g = Group.getByName(d.group)
    if d.side == h:getCoalition() and g and g:getUnit(1) then
      local r = dist(h:getPoint(), g:getUnit(1):getPoint())
      if not br or r < br then best, br = d, r end
    end
  end
  return best
end

local function list(h)
  local o = {}
  for _, d in pairs(active) do
    local g = Group.getByName(d.group)
    if d.side == h:getCoalition() and g and g:getUnit(1) then
      local p, hp = g:getUnit(1):getPoint(), h:getPoint()
      local brg = math.deg(math.atan2(p.z - hp.z, p.x - hp.x)) % 360
      o[#o + 1] = string.format("%s: пеленг %03d, %.1f км, маяк %d кГц", d.title, brg, dist(p, hp) / 1000, d.freq)
    end
  end
  msg(h, #o > 0 and ("Сбитые экипажи:\n" .. table.concat(o, "\n")) or "Сбитых экипажей нет.", 20)
end

local function signal(h, smoke)
  local d = nearest(h)
  if not d then msg(h, "Сбитых экипажей нет.", 5); return end
  local p = Group.getByName(d.group):getUnit(1):getPoint()
  if smoke then trigger.action.smoke(p, d.side == 2 and 4 or 1) else trigger.action.signalFlare(p, 1, 0) end
  msg(h, d.title .. (smoke and ": дым!" or ": ракета!"), 10)
end

local function addMenu(u)
  local ok, g = pcall(function() return u:getGroup() end)
  if not ok or not g or menus[g:getID()] then return end
  menus[g:getID()] = true
  local gid = g:getID()
  local root = missionCommands.addSubMenuForGroup(gid, "CSAR")
  missionCommands.addCommandForGroup(gid, "Сбитые экипажи", root, function() pcall(list, Unit.getByName(u:getName())) end)
  missionCommands.addCommandForGroup(gid, "Ракета у ближнего", root, function() pcall(signal, Unit.getByName(u:getName()), false) end)
  missionCommands.addCommandForGroup(gid, "Дым у ближнего", root, function() pcall(signal, Unit.getByName(u:getName()), true) end)
end

local function isHeli(u)
  local ok, desc = pcall(function() return u:getDesc() end)
  return ok and desc and desc.category == Unit.Category.HELICOPTER
end

local H = {}
function H:onEvent(e)
  local u = e.initiator
  if not u or not u.getName then return end
  local ok, name = pcall(function() return u:getName() end)
  if not ok then return end
  if e.id == world.event.S_EVENT_BIRTH then
    if isHeli(u) and u.getPlayerName and u:getPlayerName() then addMenu(u) end
  elseif e.id == world.event.S_EVENT_EJECTION then                -- катапультировался: экипаж на земле у этой точки
    local side = u:getCoalition()
    local sp = SPAWN[side]
    local id = "ej:" .. name
    if not sp or active[id] then return end
    local p = u:getPoint()
    local x, y = p.x + 30, p.z + 30
    if REDFRONT_LZ and REDFRONT_LZ.find then x, y = REDFRONT_LZ.find(x, y, 800) end   -- на открытое место
    seq = seq + 1
    local gname = "redfront csar " .. seq
    coalition.addGroup(sp.country, Group.Category.GROUND, { name = gname, task = {}, units = {
      { name = gname .. " #1", type = sp.type, x = x, y = y, heading = 0, skill = "Excellent", playerCanDrive = false } } })
    local d = { id = id, group = gname, side = side, title = "экипаж " .. u:getTypeName(), freq = freqNext }
    freqNext = freqNext - 10
    timer.scheduleFunction(function()
      pcall(setup, d)
      trigger.action.outTextForCoalition(side, "MAYDAY: " .. d.title .. " катапультировался, маяк " .. d.freq .. " кГц.", 20)
    end, nil, timer.getTime() + 3)
  elseif e.id == world.event.S_EVENT_LAND then                    -- посадка на свой аэродром - спасены
    local ob = onboard[name]
    local place = e.place
    if ob and place then
      local pn = place:getName()
      local side = u:getCoalition()
      if place:getCoalition() == side or (OWN_BASES[side] or {})[pn] then
        for id in pairs(ob) do REDFRONT_CSAR.rescued[id] = true end
        onboard[name] = nil
        msg(u, "Экипажи доставлены. Отличная работа!", 15)
      end
    end
  elseif e.id == world.event.S_EVENT_DEAD or e.id == world.event.S_EVENT_CRASH or
         (world.event.S_EVENT_UNIT_LOST and e.id == world.event.S_EVENT_UNIT_LOST) then
    for id in pairs(onboard[name] or {}) do REDFRONT_CSAR.lost[id] = true end
    onboard[name] = nil
  end
end
world.addEventHandler(H)
