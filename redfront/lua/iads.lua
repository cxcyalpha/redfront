-- redfront iads | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Сеть ПВО (идея - Skynet IADS, своя реализация). Для каждой стороны:
--   сеть - РЛС обнаружения и КРУ (наземные группы) и ДРЛО (самолёты) этой стороны;
--   ЗРК средней и большой дальности на связи (живой узел сети не дальше NET_M) молчат (тревога "зелёная" - РЛС
--   выключены), пока сеть не видит самолёт противника ближе их зоны поражения x GO_LIVE; тогда - "красная" (РЛС
--   включены), после последнего контакта держат её LINGER_S;
--   ЗРК без связи (узлы сети уничтожены или далеко) - сами по себе: РЛС включены всё время (ИИ DCS по умолчанию);
--   пуск ПРР (Weapon.GuidanceType.RADAR_PASSIVE) по направлению на ЗРК: ЗРК с вероятностью arm_p распознаёт его и
--   выключает РЛС на DARK_S (подавление: ЗРК молчит, удар проходит); ЗРК, которые сбивают ПРР (Patriot), - не выключают.
-- ЗРК малой дальности (войсковая ПВО с собственными РЛС и оптикой) - как в DCS по умолчанию, кроме реакции на ПРР.
-- Все величины - ОЦЕНКИ. Итог - REDFRONT_IADS (хук пишет в дебриф): кто когда включался, сколько раз молчал от ПРР.
REDFRONT_IADS = REDFRONT_IADS or { events = {} }
local CHECK_S, GO_LIVE, LINGER_S, NET_M, DARK_S, CONE = 5, 1.15, 60, @NET_M@, 120, math.rad(20)
local SAMS = { @SAMS@ }      -- { group, side, r (м, зона поражения), net (true - средней/большой дальности), arm_p, harm_ok }
local NET = { @NET@ }        -- { group, side, air (true - ДРЛО) }
local atan2 = math.atan2 or function(y, x) return math.atan(y, x) end   -- DCS - Lua 5.1
local state = {}             -- group -> { mode = "dark"/"live"/"auto", last = t, dark_until = t }

local function alive(name, air)
  local g = Group.getByName(name)
  if not g or not g:isExist() then return nil end
  for _, u in ipairs(g:getUnits() or {}) do
    if u and u:isExist() and u:getLife() > 0 then return g, u end
  end
  return nil
end

local function setAlarm(name, red)
  local g = Group.getByName(name)
  if not g then return end
  pcall(function()
    g:getController():setOption(AI.Option.Ground.id.ALARM_STATE,
      red and AI.Option.Ground.val.ALARM_STATE.RED or AI.Option.Ground.val.ALARM_STATE.GREEN)
  end)
end

local function pos(u) local p = u:getPoint(); return p.x, p.z end
local function dist(ax, az, bx, bz) local dx, dz = ax - bx, az - bz; return math.sqrt(dx * dx + dz * dz) end

local function contacts(side)   -- самолёты противника, которые видит сеть стороны (радаром)
  local out = {}
  for _, n in ipairs(NET) do
    if n.side == side then
      local g = alive(n.group)
      if g then
        local ok, list = pcall(function() return g:getController():getDetectedTargets(Controller.Detection.RADAR) end)
        for _, d in ipairs(ok and list or {}) do
          local o = d.object
          if o and o.isExist and o:isExist() and o.getCategory and o:getCategory() == Object.Category.UNIT
              and o:getCoalition() ~= side and o:inAir() then
            out[#out + 1] = o
          end
        end
      end
    end
  end
  return out
end

local function connected(s, sx, sz)
  for _, n in ipairs(NET) do
    if n.side == s.side then
      local g, u = alive(n.group)
      if u and (n.air or dist(sx, sz, pos(u)) <= NET_M) then return true end
    end
  end
  return false
end

local function note(s, what)
  local e = REDFRONT_IADS.events
  e[#e + 1] = { group = s.group, what = what, t = math.floor(timer.getTime()) }
end

local function check()
  local now = timer.getTime()
  local seen = { [1] = contacts(1), [2] = contacts(2) }
  for _, s in ipairs(SAMS) do
    local g, u = alive(s.group)
    if g then
      local st = state[s.group] or { mode = "init", last = -1e9, dark_until = 0 }
      state[s.group] = st
      local sx, sz = pos(u)
      local mode
      if now < st.dark_until then
        mode = "dark"
      elseif not s.net then
        mode = "auto"
      elseif not connected(s, sx, sz) then
        mode = "auto"
      else
        for _, o in ipairs(seen[s.side]) do
          if o:isExist() and dist(sx, sz, pos(o)) <= s.r * GO_LIVE then st.last = now; break end
        end
        mode = (now - st.last <= LINGER_S) and "live" or "dark"
      end
      if mode ~= st.mode then
        setAlarm(s.group, mode ~= "dark")
        if mode == "live" or mode == "auto" and st.mode == "dark" then note(s, mode) end
        st.mode = mode
      end
    end
  end
  return now + CHECK_S
end

local H = {}
function H:onEvent(e)
  if e.id ~= world.event.S_EVENT_SHOT or not e.weapon then return end
  local ok, desc = pcall(function() return e.weapon:getDesc() end)
  if not ok or not desc or desc.guidance ~= Weapon.GuidanceType.RADAR_PASSIVE then return end
  local p = e.weapon:getPoint()
  local v = e.weapon:getVelocity()
  local hdg = atan2(v.z, v.x)
  for _, s in ipairs(SAMS) do
    local g, u = alive(s.group)
    if g and not s.harm_ok then
      local sx, sz = pos(u)
      local d = dist(sx, sz, p.x, p.z)
      local b = atan2(sz - p.z, sx - p.x)
      local off = math.abs(atan2(math.sin(b - hdg), math.cos(b - hdg)))
      if d <= 120000 and off <= CONE and math.random() < s.arm_p then
        local st = state[s.group] or { mode = "init", last = -1e9, dark_until = 0 }
        state[s.group] = st
        st.dark_until = timer.getTime() + d / 600 + DARK_S     -- полёт ПРР (~600 м/с) и молчание после
        note(s, "harm")
      end
    end
  end
end
world.addEventHandler(H)
for _, s in ipairs(SAMS) do if s.net then setAlarm(s.group, false) end end   -- на связи - молчат с начала
timer.scheduleFunction(check, nil, timer.getTime() + 1)
