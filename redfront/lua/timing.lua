-- redfront timing | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Проверка плана по времени: группа ИИ выходит на свой рубеж (ИПМ, рубеж пуска, зона) - когда фактически и когда по
-- плану (ETA). Итог - REDFRONT_TIMING (хук пишет в дебриф), строка в dcs.log на каждую группу.
REDFRONT_TIMING = REDFRONT_TIMING or {}
local CHECK_S, R_M = 5, 3000
local SPECS = { @SPECS@ }   -- { group, x, y, eta }

local function check()
  local left = false
  for _, s in ipairs(SPECS) do
    if not REDFRONT_TIMING[s.group] then
      left = true
      local g = Group.getByName(s.group)
      if g and g:isExist() then
        for _, u in ipairs(g:getUnits() or {}) do
          if u and u:isExist() and u:inAir() then
            local p = u:getPoint()
            if math.sqrt((p.x - s.x) ^ 2 + (p.z - s.y) ^ 2) <= R_M then
              local t = math.floor(timer.getTime())
              REDFRONT_TIMING[s.group] = { t, s.eta }
              env.info(string.format("redfront timing: %s at %d s, planned %d s (%+d)", s.group, t, s.eta, t - s.eta))
            end
            break
          end
        end
      end
    end
  end
  if left then return timer.getTime() + CHECK_S end
  return nil
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
