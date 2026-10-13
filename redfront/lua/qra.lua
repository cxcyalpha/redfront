-- redfront qra | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Дежурные пары ПВО. Пара стоит на стоянке своего аэродрома с запущенными двигателями (поздняя активация). Раз в
-- CHECK_S секунд скрипт смотрит самолёты и вертолёты противника ближе r к аэродрому пары и спрашивает радары её
-- стороны - РЛС (EWR), РЛС обнаружения и сопровождения ЗРК, ДРЛО: если кто-то из них видит цель (радаром), пара
-- поднимается (Group.activate) - дальше её ведёт задача из .miz (зона к фронту, атака воздушных целей, посадка).
-- Кто и когда поднят - REDFRONT_QRA (хук пишет в дебриф).
REDFRONT_QRA = REDFRONT_QRA or {}
local CHECK_S = 10
local SPECS = { @SPECS@ }          -- { id, group, side, x, y, r, title }
local RADAR_ATTR = { "EWR", "SAM SR", "SAM TR", "AWACS" }

local function isRadar(u)
  for _, a in ipairs(RADAR_ATTR) do
    if u:hasAttribute(a) then return true end
  end
  return false
end

local function radars(side)        -- контроллеры групп стороны, где есть радар
  local out = {}
  for _, cat in ipairs({ Group.Category.GROUND, Group.Category.AIRPLANE }) do
    for _, g in ipairs(coalition.getGroups(side, cat) or {}) do
      for _, u in ipairs(g:getUnits() or {}) do
        if u and u:isExist() and isRadar(u) then out[#out + 1] = g:getController(); break end
      end
    end
  end
  return out
end

local function enemies(side, x, y, r)
  local foe = side == 1 and 2 or 1
  local out = {}
  for _, cat in ipairs({ Group.Category.AIRPLANE, Group.Category.HELICOPTER }) do
    for _, g in ipairs(coalition.getGroups(foe, cat) or {}) do
      for _, u in ipairs(g:getUnits() or {}) do
        if u and u:isExist() and u:inAir() then
          local p = u:getPoint()
          local dx, dz = p.x - x, p.z - y
          if dx * dx + dz * dz <= r * r then out[#out + 1] = u end
        end
      end
    end
  end
  return out
end

local function check()
  local left = false
  local cache = {}
  for _, s in ipairs(SPECS) do
    if not REDFRONT_QRA[s.id] then
      left = true
      local targets = enemies(s.side, s.x, s.y, s.r)
      if #targets > 0 then
        cache[s.side] = cache[s.side] or radars(s.side)
        local seen
        for _, c in ipairs(cache[s.side]) do
          for _, t in ipairs(targets) do
            local ok, det = pcall(function() return c:isTargetDetected(t, Controller.Detection.RADAR) end)
            if ok and det then seen = t; break end
          end
          if seen then break end
        end
        if seen then
          local g = Group.getByName(s.group)
          if g then g:activate() end
          REDFRONT_QRA[s.id] = math.floor(timer.getTime())
          env.info("redfront qra: " .. s.title .. " - взлёт по " .. seen:getTypeName())
        end
      end
    end
  end
  if left then return timer.getTime() + CHECK_S end
  return nil
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
