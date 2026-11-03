-- redfront gci | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Наземное наведение истребителей ИИ (КРУ, GCI) - замена ДРЛО для стороны без него. Раз в CHECK_S секунд для каждой
-- стороны с наведением: самолёты и вертолёты противника, которых видят НАЗЕМНЫЕ РЛС стороны (РЛС обнаружения, РЛС
-- обнаружения ЗРК; видимость - модель DCS: радиогоризонт, рельеф, малая высота). Наводящий не бросает пару на любую
-- отметку, а решает, как пункт наведения:
--   граница   - цель не дальше leash от своих РЛС (над своей территорией и зонтиком ЗРК, не за линию фронта);
--   приоритет - ударные самолёты важнее истребителей, идущие к своим объектам (аэродромы, ЗРК) - важнее уходящих,
--               ДРЛО и заправщики - ценные; вертолёты - только если доктрина их перехватывает (heli);
--   силы      - группа противника у цели (в GROUP_M) не больше odds x наших самолётов; больше - только атака с одного
--               захода (hit_run доктрины: атака и выход), иначе не наводим;
--   пара      - без ракет и снарядов или с топливом ниже bingo - не наводим (она идёт домой);
--   сосредоточение - на крупную группу (от 4 самолётов) - до per_target пар, на мелкую - одна.
-- Пилот получает задачу AttackGroup (знает, где цель, как по командам с земли); цель пропала с РЛС или ушла за
-- границу - наведение снято (popTask), пара продолжает свою задачу. Каналов наведения у стороны - channels.
-- Итог - REDFRONT_GCI (хук пишет в дебриф). Все величины - ОЦЕНКИ доктрины (gci).
REDFRONT_GCI = REDFRONT_GCI or { events = {} }
local CHECK_S, GROUP_M = 15, 10000
local FIGHTERS = { @FIGHTERS@ }   -- { group, side }
local SIDES = { @SIDES@ }         -- [сторона] = { channels, commit, leash (м), odds, hit_run, heli, bingo, per_target }
local PROTECT = { @PROTECT@ }     -- [сторона] = { {x, y}, ... } - свои объекты (аэродромы, ЗРК)
local RADAR_ATTR = { "EWR", "SAM SR" }
local assigned = {}               -- группа истребителей -> { target = группа цели, unit = единица цели }

local function d2(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.z - b.z) ^ 2) end

local function groundRadars(side)
  local ctrl, pos = {}, {}
  for _, g in ipairs(coalition.getGroups(side, Group.Category.GROUND) or {}) do
    for _, u in ipairs(g:getUnits() or {}) do
      local ok = false
      if u and u:isExist() then
        for _, a in ipairs(RADAR_ATTR) do if u:hasAttribute(a) then ok = true end end
      end
      if ok then ctrl[#ctrl + 1] = g:getController(); pos[#pos + 1] = u:getPoint(); break end
    end
  end
  return ctrl, pos
end

local function picture(side)      -- единицы противника в воздухе, которых видят наземные РЛС стороны
  local seen, list = {}, {}
  local ctrl, rpos = groundRadars(side)
  for _, c in ipairs(ctrl) do
    local ok, dets = pcall(function() return c:getDetectedTargets(Controller.Detection.RADAR) end)
    for _, d in ipairs(ok and dets or {}) do
      local o = d.object
      if o and o.isExist and o:isExist() and o.getCoalition and o:getCoalition() ~= side and o.inAir and o:inAir() then
        local n = o:getName()
        if not seen[n] then seen[n] = true; list[#list + 1] = o end
      end
    end
  end
  return list, seen, rpos
end

local function has(u, a) local ok, r = pcall(function() return u:hasAttribute(a) end); return ok and r end

local function value(t, prm)      -- ценность цели: 0 - не перехватываем
  if has(t, "Helicopters") then return prm.heli and 1 or 0 end
  if has(t, "AWACS") or has(t, "Tankers") then return 3 end
  if has(t, "Bombers") or has(t, "Strategic bombers") then return 3 end
  if has(t, "Fighters") or has(t, "Interceptors") then return 1 end
  if has(t, "Multirole fighters") then return 2 end   -- F-4, F-16 - чаще всего ударная группа
  return 2
end

local function inbound(side, t)   -- цель идёт к своему объекту (вектор скорости - на ближний объект ближе 60 град.)
  local p, v = t:getPoint(), t:getVelocity()
  local sp = math.sqrt(v.x ^ 2 + v.z ^ 2)
  if sp < 30 then return false end
  local best, bd = nil, math.huge
  for _, o in ipairs(PROTECT[side] or {}) do
    local d = math.sqrt((o.x - p.x) ^ 2 + (o.y - p.z) ^ 2)
    if d < bd then best, bd = o, d end
  end
  if not best then return false end
  local cosv = ((best.x - p.x) * v.x + (best.y - p.z) * v.z) / (bd * sp + 1)
  return cosv > 0.5
end

local function nearRadar(rpos, p, leash)
  for _, r in ipairs(rpos) do if d2(r, p) <= leash then return true end end
  return false
end

local function enemiesAround(list, p)   -- самолётов противника у цели (её группа и те, кто рядом)
  local n = 0
  for _, t in ipairs(list) do if d2(t:getPoint(), p) <= GROUP_M then n = n + 1 end end
  return n
end

local function ready(g, prm)      -- самолёты пары в воздухе с боеприпасами и топливом выше bingo
  local n, lead = 0, nil
  for _, u in ipairs(g:getUnits() or {}) do
    if u and u:isExist() and u:inAir() then
      local ammo = u:getAmmo()
      if ammo and #ammo > 0 and (u:getFuel() or 1) >= prm.bingo then
        n = n + 1
        lead = lead or u
      end
    end
  end
  return n, lead
end

local function check()
  local pics = {}
  for side, prm in pairs(SIDES) do
    local list, seen, rpos = picture(side)
    pics[side] = { list = list, seen = seen, rpos = rpos, busy = 0, prm = prm, on = {} }
  end
  for _, f in ipairs(FIGHTERS) do                -- снять наведение: цель пропала с РЛС, ушла за границу, пара не готова
    local a = assigned[f.group]
    if a then
      local g = Group.getByName(f.group)
      local p = pics[f.side]
      local keep = g and g:isExist() and p and p.seen[a.unit]
      if keep then
        local tu = Unit.getByName(a.unit)
        keep = tu and nearRadar(p.rpos, tu:getPoint(), p.prm.leash) and select(1, ready(g, p.prm)) > 0
      end
      if not keep then
        if g and g:isExist() then pcall(function() g:getController():popTask() end) end
        assigned[f.group] = nil
        REDFRONT_GCI.events[#REDFRONT_GCI.events + 1] = { t = math.floor(timer.getTime()), group = f.group, lost = a.unit }
      else
        p.busy = p.busy + 1
        p.on[a.target] = (p.on[a.target] or 0) + 1
      end
    end
  end
  for _, f in ipairs(FIGHTERS) do                -- назначить цели свободным парам
    local p = pics[f.side]
    local g = Group.getByName(f.group)
    if p and not assigned[f.group] and p.busy < p.prm.channels and g and g:isExist() then
      local n, lead = ready(g, p.prm)
      if lead then
        local lp, prm = lead:getPoint(), p.prm
        local best, bscore, bhit
        for _, t in ipairs(p.list) do
          local tp, tg = t:getPoint(), t.getGroup and t:getGroup()
          local d = d2(tp, lp)
          local v = value(t, prm)
          if tg and v > 0 and d <= prm.commit and nearRadar(p.rpos, tp, prm.leash) then
            local foes = enemiesAround(p.list, tp)
            local cap = foes >= 4 and prm.per_target or 1
            local hit = foes > prm.odds * n
            if (p.on[tg:getName()] or 0) < cap and (not hit or prm.hit_run) then
              local score = v * 100 + (inbound(f.side, t) and 150 or 0) - d / 1000 - (hit and 80 or 0)
              if not bscore or score > bscore then best, bscore, bhit = t, score, hit end
            end
          end
        end
        if best then
          local tg = best:getGroup()
          local params = { groupId = tg:getID() }
          if bhit then params.attackQtyLimit, params.attackQty = true, 1 end   -- с одного захода: атака и выход
          local ok = pcall(function() g:getController():pushTask({ id = "AttackGroup", params = params }) end)
          if ok then
            assigned[f.group] = { target = tg:getName(), unit = best:getName() }
            p.busy = p.busy + 1
            p.on[tg:getName()] = (p.on[tg:getName()] or 0) + 1
            local km = math.floor(d2(best:getPoint(), lp) / 1000)
            REDFRONT_GCI.events[#REDFRONT_GCI.events + 1] = { t = math.floor(timer.getTime()), group = f.group,
                                                              target = best:getTypeName(), km = km, hit_run = bhit or nil }
            env.info("redfront gci: " .. f.group .. " -> " .. best:getTypeName() .. " " .. km .. " km" .. (bhit and " (one pass)" or ""))
          end
        end
      end
    end
  end
  return timer.getTime() + CHECK_S
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
