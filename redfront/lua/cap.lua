-- redfront cap | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Пары прикрытия ИИ (прикрытие войск, прикрытие и расчистка в пакете): уходят с зоны домой, если пара потеряла
-- самолёт (одиночка в зоне не дежурит). Остаток топлива и расход ракет - опции DCS группы (RTB on bingo / out of
-- AAM, build). Смена приходит по плану полётов до ухода предыдущей (ato.RELIEF_OVERLAP_S).
local CHECK_S = 10
local SPECS = { @SPECS@ }   -- { group, size, zone (номер точки зоны), home (номер точки посадки), side, title }
local gone = {}

local function count(g)
  local n = 0
  for _, u in ipairs(g:getUnits() or {}) do
    if u and u:isExist() and u:getLife() > 0 then n = n + 1 end
  end
  return n
end

local function check()
  for _, s in ipairs(SPECS) do
    if not gone[s.group] then
      local g = Group.getByName(s.group)
      if g and g:isExist() then
        local n = count(g)
        if n > 0 and n < s.size then
          gone[s.group] = true
          pcall(function()
            g:getController():setCommand({ id = "SwitchWaypoint",
              params = { fromWaypointIndex = s.zone, goToWaypointIndex = s.home } })
          end)
          if trigger.action.outTextForCoalition then
            trigger.action.outTextForCoalition(s.side, s.title .. ": потерян ведомый - уходим домой", 10)
          end
          env.info("redfront cap: " .. s.group .. " - wingman lost, RTB")
        end
      end
    end
  end
  return timer.getTime() + CHECK_S
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
