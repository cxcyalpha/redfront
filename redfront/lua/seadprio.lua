-- redfront seadprio | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Порядок целей групп подавления ПВО (ОЦЕНКИ). Задачи миссии уже по плану: главный ЗРК - приоритет 0, следующие -
-- 1, 2..., прочие РЛС района - после них (build.py). Здесь - одно исключение: незапланированный ЗРК пустил ракету
-- по самолёту звена - звено отвечает ему вне очереди (одна атака на этот ЗРК, SELF_PASSES заходов), затем
-- возвращается к плану. Запланированный ЗРК, стреляющий по звену, - и так в плане, его не трогаем.
-- Итог - REDFRONT_SEADPRIO.events (ответы вне очереди).
REDFRONT_SEADPRIO = REDFRONT_SEADPRIO or { events = {} }
local SPECS = { @SPECS@ }   -- { group = звено, sams = { группы ЗРК по плану } }
local SELF_PASSES = 1
local by_group, answered = {}, {}
for _, s in ipairs(SPECS) do
  local planned = {}
  for _, n in ipairs(s.sams) do planned[n] = true end
  by_group[s.group] = { planned = planned }
end

local function gname(o)
  local ok, n = pcall(function() return o:getGroup():getName() end)
  return ok and n or nil
end

local H = {}
function H:onEvent(e)
  if e.id ~= world.event.S_EVENT_SHOT or not e.initiator or not e.weapon then return end
  local ok, tgt = pcall(function() return e.weapon:getTarget() end)
  if not ok or not tgt then return end
  local fg = gname(tgt)
  local spec = fg and by_group[fg]
  if not spec then return end
  local okc, cat = pcall(function() return e.initiator:getGroup():getCategory() end)
  if not okc or cat ~= Group.Category.GROUND then return end
  local sam = gname(e.initiator)
  if not sam or spec.planned[sam] then return end      -- запланированный - и так по плану
  local key = fg .. "|" .. sam
  if answered[key] then return end
  answered[key] = true
  local g, sg = Group.getByName(fg), Group.getByName(sam)
  if not (g and g:isExist() and sg and sg:isExist()) then return end
  pcall(function()
    g:getController():pushTask({ id = "AttackGroup", params = { groupId = sg:getID(), weaponType = 9663676414,
      expend = "Auto", attackQtyLimit = true, attackQty = SELF_PASSES } })
  end)
  local ev = REDFRONT_SEADPRIO.events
  ev[#ev + 1] = { group = fg, sam = sam, what = "self_defense", t = math.floor(timer.getTime()) }
end
world.addEventHandler(H)
