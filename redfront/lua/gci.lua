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
-- картина обстановки, ценность и курс целей, свои объекты - airpic.lua (RF_AIR)
local assigned = {}               -- группа истребителей -> { target = группа цели, unit = единица цели }
local d2 = RF_AIR.d2

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
    local pic = RF_AIR.picture(side, false)       -- только наземные РЛС: наведение с земли
    pics[side] = { list = pic.list, seen = pic.seen, rpos = pic.rpos, busy = 0, prm = prm, on = {} }
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
          local v = RF_AIR.value(t, prm.heli)
          if tg and v > 0 and d <= prm.commit and nearRadar(p.rpos, tp, prm.leash) then
            local foes = enemiesAround(p.list, tp)
            local cap = foes >= 4 and prm.per_target or 1
            local hit = foes > prm.odds * n
            if (p.on[tg:getName()] or 0) < cap and (not hit or prm.hit_run) then
              local score = v * 100 + (RF_AIR.inbound(f.side, t) and 150 or 0) - d / 1000 - (hit and 80 or 0)
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
