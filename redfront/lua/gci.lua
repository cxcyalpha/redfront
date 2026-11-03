-- redfront gci | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Наземное наведение истребителей ИИ (КРУ, GCI) - замена ДРЛО для стороны без него. Раз в CHECK_S секунд для каждой
-- стороны с наведением: самолёты и вертолёты противника, которых видят НАЗЕМНЫЕ РЛС стороны (РЛС обнаружения, РЛС
-- обнаружения ЗРК; видимость - модель DCS: радиогоризонт, рельеф, малая высота), - цели наведения. Истребитель ИИ в
-- воздухе (дежурные пары, пары прикрытия) без цели получает ближнюю цель в радиусе commit (задача AttackGroup - пилот
-- знает, где цель, как по командам с земли). Каналов наведения у стороны - channels (одновременно наводимых групп);
-- цель пропала с РЛС - наведение снято (popTask), пара продолжает свою задачу. Итог - REDFRONT_GCI (хук пишет в дебриф).
-- Все величины - ОЦЕНКИ доктрины (gci: channels, commit_km).
REDFRONT_GCI = REDFRONT_GCI or { events = {} }
local CHECK_S = 15
local FIGHTERS = { @FIGHTERS@ }   -- { group, side }
local SIDES = { @SIDES@ }         -- [сторона] = { channels, commit (м) }
local RADAR_ATTR = { "EWR", "SAM SR" }
local assigned = {}               -- группа истребителей -> { target = имя группы цели, unit = имя единицы цели }

local function groundRadars(side)
  local out = {}
  for _, g in ipairs(coalition.getGroups(side, Group.Category.GROUND) or {}) do
    for _, u in ipairs(g:getUnits() or {}) do
      local ok = false
      if u and u:isExist() then
        for _, a in ipairs(RADAR_ATTR) do if u:hasAttribute(a) then ok = true end end
      end
      if ok then out[#out + 1] = g:getController(); break end
    end
  end
  return out
end

local function picture(side)      -- единицы противника в воздухе, которых видят наземные РЛС стороны
  local seen, list = {}, {}
  for _, c in ipairs(groundRadars(side)) do
    local ok, dets = pcall(function() return c:getDetectedTargets(Controller.Detection.RADAR) end)
    for _, d in ipairs(ok and dets or {}) do
      local o = d.object
      if o and o.isExist and o:isExist() and o.getCoalition and o:getCoalition() ~= side and o.inAir and o:inAir() then
        local n = o:getName()
        if not seen[n] then seen[n] = true; list[#list + 1] = o end
      end
    end
  end
  return list, seen
end

local function airborne(g)
  for _, u in ipairs(g:getUnits() or {}) do
    if u and u:isExist() and u:inAir() then return u end
  end
  return nil
end

local function check()
  local pics = {}
  for side, prm in pairs(SIDES) do
    local list, seen = picture(side)
    pics[side] = { list = list, seen = seen, busy = 0, prm = prm }
  end
  for _, f in ipairs(FIGHTERS) do                -- снять наведение: цель пропала с РЛС или группа погибла
    local a = assigned[f.group]
    if a then
      local g = Group.getByName(f.group)
      local p = pics[f.side]
      if not g or not g:isExist() or not airborne(g) or not (p and p.seen[a.unit]) then
        if g and g:isExist() then pcall(function() g:getController():popTask() end) end
        assigned[f.group] = nil
        REDFRONT_GCI.events[#REDFRONT_GCI.events + 1] = { t = math.floor(timer.getTime()), group = f.group, lost = a.unit }
      elseif p then
        p.busy = p.busy + 1
      end
    end
  end
  for _, f in ipairs(FIGHTERS) do                -- назначить цели свободным истребителям
    local p = pics[f.side]
    local g = Group.getByName(f.group)
    if p and not assigned[f.group] and p.busy < p.prm.channels and g and g:isExist() then
      local lead = airborne(g)
      if lead then
        local lp, best, bd = lead:getPoint(), nil, p.prm.commit
        for _, t in ipairs(p.list) do
          local tp = t:getPoint()
          local d = math.sqrt((tp.x - lp.x) ^ 2 + (tp.z - lp.z) ^ 2)
          if d < bd then best, bd = t, d end
        end
        if best and best.getGroup and best:getGroup() then
          local ok = pcall(function()
            g:getController():pushTask({ id = "AttackGroup", params = { groupId = best:getGroup():getID() } })
          end)
          if ok then
            assigned[f.group] = { target = best:getGroup():getName(), unit = best:getName() }
            p.busy = p.busy + 1
            REDFRONT_GCI.events[#REDFRONT_GCI.events + 1] = { t = math.floor(timer.getTime()), group = f.group,
                                                              target = best:getTypeName(), km = math.floor(bd / 1000) }
            env.info("redfront gci: " .. f.group .. " -> " .. best:getTypeName() .. " " .. math.floor(bd / 1000) .. " km")
          end
        end
      end
    end
  end
  return timer.getTime() + CHECK_S
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
