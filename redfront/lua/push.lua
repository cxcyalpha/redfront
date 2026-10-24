-- redfront push | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Удар по готовности подавления ПВО. Ударные группы ИИ пакета ждут на ИПМ (круг до флага), пока РЛС всех ЗРК,
-- которые прикрывают цель (sams: группа и её РЛС), не уничтожены или не молчат под ПРР (iads.lua: REDFRONT_IADS.dark).
-- Подавление стреляет, но подавлены не все - удар через SUPPRESS_WAIT_S после первого пуска (окно подавления).
-- Все группы подавления сбиты, не выстрелив, - удар отменяется: ударные уходят домой (переход на точку посадки).
-- К сроку ничего из этого - удар по сроку (РЛС молчат сами). Итог - REDFRONT_PUSH (хук пишет в дебриф).
REDFRONT_PUSH = REDFRONT_PUSH or {}
local CHECK_S, SUPPRESS_WAIT_S = 5, 120   -- ОЦЕНКА: окно подавления после первого пуска ПРР
local SPECS = { @SPECS@ }   -- { id, side, title, flag, strikes = {}, ip = {}, home = {}, sead = {}, sead_start = {}, deadline }
local SAY = {
  clear = "РЛС ЗРК у цели уничтожены или подавлены - удар разрешён",
  sead = "подавление ПВО ведёт пуски - удар в окне подавления",
  deadline = "пусков подавления нет, РЛС ПВО молчат - удар по времени",
  abort = "группы подавления ПВО сбиты - удар отменён, ударным группам - домой",
}

local function alive(name)
  local g = Group.getByName(name)
  if not g or not g:isExist() then return false end
  for _, u in ipairs(g:getUnits() or {}) do
    if u and u:isExist() and u:getLife() > 0 then return true end
  end
  return false
end

local function push(s, how)
  if REDFRONT_PUSH[s.id] then return end
  REDFRONT_PUSH[s.id] = how
  if how == "abort" then
    for i, n in ipairs(s.strikes) do
      local g = Group.getByName(n)
      if g and g:isExist() then
        pcall(function()
          g:getController():setCommand({ id = "SwitchWaypoint",
            params = { fromWaypointIndex = s.ip[i], goToWaypointIndex = s.home[i] } })
        end)
      end
    end
  end
  trigger.action.setUserFlag(s.flag, true)
  if trigger.action.outTextForCoalition then
    trigger.action.outTextForCoalition(s.side, s.title .. ": " .. SAY[how], 15)
  end
  env.info("redfront push: " .. s.id .. " - " .. how)
end

local H = {}
function H:onEvent(e)
  if e.id ~= world.event.S_EVENT_SHOT or not e.initiator then return end
  local ok, gname = pcall(function() return e.initiator:getGroup():getName() end)
  if not ok or not gname then return end
  for _, s in ipairs(SPECS) do
    for _, n in ipairs(s.sead) do
      if n == gname and not s.first_shot then s.first_shot = timer.getTime() end
    end
  end
end
world.addEventHandler(H)

local function unit_alive(name)
  local u = Unit.getByName(name)
  return u and u:isExist() and u:getLife() > 0
end

local function suppressed(s)               -- все прикрывающие ЗРК без РЛС (уничтожены) или молчат под ПРР
  if not s.sams or #s.sams == 0 then return false end
  local now = timer.getTime()
  local dark = (REDFRONT_IADS and REDFRONT_IADS.dark) or {}
  for _, z in ipairs(s.sams) do
    local up = false
    for _, r in ipairs(z.radars) do
      if unit_alive(r) then up = true end
    end
    if up and not ((dark[z.group] or 0) > now) then return false end
  end
  return true
end

local function check()
  local left = false
  local now = timer.getTime()
  for _, s in ipairs(SPECS) do
    if not REDFRONT_PUSH[s.id] then
      left = true
      local any = false
      for i, n in ipairs(s.sead) do
        if now < s.sead_start[i] + 60 or alive(n) then any = true end   -- до взлёта группы в миссии её нет
      end
      if suppressed(s) then
        push(s, "clear")
      elseif s.first_shot and now >= s.first_shot + SUPPRESS_WAIT_S then
        push(s, "sead")
      elseif not any then
        push(s, "abort")
      elseif now >= s.deadline then
        push(s, "deadline")
      end
    end
  end
  if left then return now + CHECK_S end
  return nil
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
