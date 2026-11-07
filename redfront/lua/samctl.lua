-- redfront samctl | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Управление огнём ПВО поверх ИИ DCS (ОЦЕНКИ):
--   1. Реакция: от первого обнаружения цели своей РЛС (или оптикой) до разрешения огня - delay (зависит от типа ЗРК,
--      выучки расчёта и тревоги: держали цель недавно - быстрее). До этого - огонь запрещён (ROE WEAPON_HOLD).
--   2. Дальность: огонь - только по цели ближе k_range x зоны поражения (не пуск на предельной дальности).
--   3. Зенитная артиллерия: заградительный огонь (FireAtPoint на высоте цели, с упреждением, с разбросом) вместо
--      прицельного - огонь по самолётам ИИ DCS запрещён; заграждение ставится по ближней цели раз в BARRAGE_S.
--   4. Стрельба с переездом (подвижные ЗРК: Куб, Оса...): после SCOOT_SHOTS пусков - РЛС выключены, переезд на
--      SCOOT_M и тишина SCOOT_MIN..SCOOT_MAX с (iads.lua не включает их на это время).
--   6. ПЗРК: огонь - по цели ближе MANPAD_M и медленнее MANPAD_V, не больше MANPAD_SHOTS пусков на группу за миссию.
--   7. Помехи (РЭБ): постановщик вне зоны (JAMS) - по всем целям в его секторе, самолётная станция помех (SELFJ) -
--      только по своему самолёту. Помеха удлиняет реакцию и сокращает рубеж пуска, но не запрещает огонь:
--      ближе рубежа прожига (BURN x зоны) помехи нет; сила помехи ограничена JAM_MAX, две и больше станций
--      складываются с убыванием; помехозащищённость ЗРК (eccm) ослабляет помеху. Помехи не действуют на
--      оптику и ПЗРК, и на зенитки ближе прожига.
-- Итог - REDFRONT_SAMCTL (хук пишет в дебриф).
REDFRONT_SAMCTL = REDFRONT_SAMCTL or { scoot = {}, events = {} }
local CHECK_S, BARRAGE_S, FORGET_S = 2, 8, 90
local SCOOT_SHOTS, SCOOT_M, SCOOT_MIN, SCOOT_MAX = 2, 1500, 300, 600
local MANPAD_M, MANPAD_V, MANPAD_SHOTS = 4500, 300, 2
local SPECS = { @SPECS@ }   -- { group, kind = sam|aaa|manpad, r (м), k_range, delay (с), mobile }
local st = {}               -- группа -> { first, last, open, shots, scoot_until }

local function grp(n) local g = Group.getByName(n); if g and g:isExist() then return g end end
local function lead(g)
  for _, u in ipairs(g:getUnits() or {}) do if u and u:isExist() and u:getLife() > 0 then return u end end
end
local function d2(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.z - b.z) ^ 2) end
local function setROE(g, open)
  pcall(function()
    g:getController():setOption(AI.Option.Ground.id.ROE,
      open and AI.Option.Ground.val.ROE.OPEN_FIRE or AI.Option.Ground.val.ROE.WEAPON_HOLD)
  end)
end
local function note(s, what) local e = REDFRONT_SAMCTL.events; e[#e + 1] = { group = s.group, what = what, t = math.floor(timer.getTime()) } end

-- ОЦЕНКИ РЭБ: потолок силы помехи, прожиг (доля зоны поражения), сектор постановщика (cos половины угла), дальность
-- действия постановщика, предел удлинения реакции и предел сокращения рубежа - чтобы помехи не делали ПВО слепой
local JAM_MAX, BURN, JAM_COS, JAM_RANGE_M, DELAY_MAX_K, RANGE_MIN_K = 0.6, 0.35, math.cos(math.rad(15)), 150000, 2.0, 0.45
local SELFJ = { @SELFJ@ }   -- тип DCS -> сила самолётной станции помех
local JAMS = { @JAMS@ }     -- группы постановщиков помех
local SOJ_POWER = 0.5

local function jammers()
  local out = {}
  for _, n in ipairs(JAMS) do
    local g = grp(n)
    for _, u in ipairs(g and g:getUnits() or {}) do
      if u and u:isExist() and u:inAir() then out[#out + 1] = u end
    end
  end
  return out
end

-- сила помехи для ЗРК s (позиция up) по цели o на дальности bd: 0..JAM_MAX
local function jam_of(s, up, o, bd, sojs)
  if bd <= s.r * BURN then return 0 end                -- прожиг: на малой дальности отражение сильнее помехи
  local sum = {}
  local okt, tn = pcall(function() return o:getTypeName() end)
  local self_p = okt and SELFJ[tn] or nil
  if self_p then sum[#sum + 1] = self_p end
  local op = o:getPoint()
  local tx, tz = op.x - up.x, op.z - up.z
  for _, j in ipairs(sojs) do
    if j:getCoalition() == o:getCoalition() then
      local jp = j:getPoint()
      local jx, jz = jp.x - up.x, jp.z - up.z
      local dj = math.sqrt(jx * jx + jz * jz)
      if dj > 1 and dj <= JAM_RANGE_M and (jx * tx + jz * tz) / (dj * bd) >= JAM_COS then
        sum[#sum + 1] = SOJ_POWER * math.min(1, bd / dj)  -- дальше цель от ЗРК, ближе постановщик - помеха сильнее
      end
    end
  end
  table.sort(sum, function(a, b) return a > b end)
  local p, w = 0, 1
  for _, v in ipairs(sum) do p = p + v * w; w = w * 0.5 end   -- каждая следующая станция - вдвое слабее
  return math.min(JAM_MAX, p * (1 - (s.eccm or 0)))
end

local function targets(g)
  local out = {}
  local ok, list = pcall(function() return g:getController():getDetectedTargets() end)
  for _, d in ipairs(ok and list or {}) do
    local o = d.object
    if o and o.isExist and o:isExist() and o.getCategory and o:getCategory() == Object.Category.UNIT and o.inAir and o:inAir() then
      out[#out + 1] = o
    end
  end
  return out
end

local function barrage(g, u, o, s)
  local p, v = o:getPoint(), o:getVelocity()
  local d = d2(p, u:getPoint())
  local tof = d / 900                                    -- ОЦЕНКА: полёт снаряда ~900 м/с
  local aim = { x = p.x + v.x * tof, y = p.z + v.z * tof }
  local r = 150 + d * 0.05                               -- разброс растёт с дальностью
  pcall(function()
    g:getController():pushTask({ id = "FireAtPoint", params = { point = aim, radius = r, expendQty = 40,
      expendQtyEnabled = true, altitude = p.y, alt_type = 0 } })
  end)
end

local function scoot(g, u, s, now)
  local p = u:getPoint()
  local a = math.random() * 2 * math.pi
  local to = { x = p.x + math.cos(a) * SCOOT_M, y = p.z + math.sin(a) * SCOOT_M }
  pcall(function()
    g:getController():setOption(AI.Option.Ground.id.ALARM_STATE, AI.Option.Ground.val.ALARM_STATE.GREEN)
    g:getController():setTask({ id = "Mission", params = { route = { points = {
      { x = p.x, y = p.z, type = "Turning Point", action = "Off Road", speed = 10 },
      { x = to.x, y = to.y, type = "Turning Point", action = "Off Road", speed = 10 } } } } })
  end)
  local quiet = SCOOT_MIN + math.random() * (SCOOT_MAX - SCOOT_MIN)
  REDFRONT_SAMCTL.scoot[s.group] = now + quiet
  note(s, "scoot")
end

local function check()
  local now = timer.getTime()
  local sojs = jammers()
  for _, s in ipairs(SPECS) do
    local g = grp(s.group)
    local u = g and lead(g)
    if u then
      local c = st[s.group] or { first = nil, last = -1e9, open = nil, shots = 0, b = 0 }
      st[s.group] = c
      local up = u:getPoint()
      local best, bd = nil, math.huge
      for _, o in ipairs(targets(g)) do
        if o:getCoalition() ~= u:getCoalition() then
          local d = d2(o:getPoint(), up)
          if d < bd then best, bd = o, d end
        end
      end
      if best then
        if not c.first or now - c.last > FORGET_S then c.first = now end
        c.last = now
      end
      local open = false
      if (REDFRONT_SAMCTL.scoot[s.group] or 0) > now then
        open = false                                      -- переезд: молчим
      elseif s.kind == "manpad" or s.kind == "aaa" then
        local v = best and best:getVelocity()
        local spd = v and math.sqrt(v.x ^ 2 + v.y ^ 2 + v.z ^ 2) or 0
        -- ПЗРК (и ПЗРК при зенитках): близкая и не слишком быстрая цель, не больше MANPAD_SHOTS пусков
        open = s.manpad and best ~= nil and c.shots < MANPAD_SHOTS and bd <= MANPAD_M and spd <= MANPAD_V
               and now - c.first >= s.delay or false
      end
      if s.kind == "aaa" and not open then              -- зенитки: прицельно - нет; заграждение
        if best and bd <= s.r and now - c.first >= s.delay and now - c.b >= BARRAGE_S then
          barrage(g, u, best, s)
          c.b = now
        end
      elseif s.kind == "sam" and (REDFRONT_SAMCTL.scoot[s.group] or 0) <= now then
        local j = best and jam_of(s, up, best, bd, sojs) or 0
        local kr = math.max(RANGE_MIN_K, s.k_range * (1 - j))       -- рубеж пуска под помехой - ближе, но не ближе предела
        local dl = s.delay * math.min(DELAY_MAX_K, 1 + j * 1.5)      -- реакция под помехой - дольше, но не дольше предела
        open = best ~= nil and bd <= s.r * kr and now - c.first >= dl
        if j > 0 and best and bd <= s.r * s.k_range and not open and not c.jn then c.jn = true; note(s, "jammed") end
        if j == 0 then c.jn = nil end
      end
      if open ~= c.open then
        setROE(g, open)
        c.open = open
        if open then note(s, "fire") end
      end
    end
  end
  return now + CHECK_S
end

local H = {}
function H:onEvent(e)
  if e.id ~= world.event.S_EVENT_SHOT or not e.initiator then return end
  local ok, gn = pcall(function() return e.initiator:getGroup():getName() end)
  if not ok or not gn then return end
  for _, s in ipairs(SPECS) do
    if s.group == gn then
      local c = st[gn] or { shots = 0, last = -1e9, b = 0 }
      st[gn] = c
      c.shots = (c.shots or 0) + 1
      if s.manpad and s.kind ~= "sam" and c.shots >= MANPAD_SHOTS then
        local g = grp(gn); if g then setROE(g, false) end; c.open = false; note(s, "manpad_out")
      elseif s.mobile and c.shots >= SCOOT_SHOTS then
        local g = grp(gn); local u = g and lead(g)
        if u then scoot(g, u, s, timer.getTime()); c.shots = 0; c.open = false; setROE(g, false) end
      end
    end
  end
end
world.addEventHandler(H)
for _, s in ipairs(SPECS) do local g = grp(s.group); if g then setROE(g, false) end end   -- до обнаружения - огонь запрещён
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
