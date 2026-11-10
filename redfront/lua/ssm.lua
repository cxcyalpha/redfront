-- redfront ssm | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Пуски оперативно-тактических ракет (Скад, Точка, Искандер) по плану суток (strategic.py): в своё время пусковая
-- получает FireAtPoint по цели (одна ракета). Пусковая уничтожена - пуска нет (кампания учтёт по дебрифу).
-- Итог - REDFRONT_SSM.events (выполненные пуски).
REDFRONT_SSM = REDFRONT_SSM or { events = {} }
local SPECS = { @SPECS@ }   -- { group, x, y, at (с от начала миссии), target }

local function fire(s)
  local g = Group.getByName(s.group)
  if not (g and g:isExist()) then return end
  local alive = false
  for _, u in ipairs(g:getUnits() or {}) do if u and u:isExist() and u:getLife() > 0 then alive = true end end
  if not alive then return end
  pcall(function()
    g:getController():pushTask({ id = "FireAtPoint", params = { point = { x = s.x, y = s.y }, radius = 50,
      expendQty = 1, expendQtyEnabled = true } })
  end)
  local e = REDFRONT_SSM.events
  e[#e + 1] = { group = s.group, target = s.target, t = math.floor(timer.getTime()) }
end

for _, s in ipairs(SPECS) do
  timer.scheduleFunction(function() fire(s) end, nil, timer.getTime() + math.max(5, s.at))
end
