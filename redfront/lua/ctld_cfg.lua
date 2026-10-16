-- redfront ctld | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Настройка CTLD (Ciribob, Zip, VEAF: github.com/ciribob/DCS-CTLD, lua/ctld/NOTICE.md) под вылет игрока. Нужны
-- mist.lua и CTLD.lua (в копии миссии ctld.dontInitialize = true) - раньше этого скрипта. Меню CTLD - оригинальные.
--   * десант (assault.lua): игрок грузит свою долю роты в зоне погрузки у своей стоянки (меню F10 "CTLD"
--     -> "Десант"), высаживает на площадке; севший на площадке десант CTLD заменяется фигурами роты из модели
--     (REDFRONT_ASSAULT_CTLD в assault.lua) - их потери считает хук;
--   * перевозка снабжения: ящики "Supply" - у машины тыла рядом со стоянкой игрока, доставка - на аэродром
--     назначения (зона выгрузки). Сколько кг лежит в зоне (ящики) и распаковано в ней - REDFRONT_LIFT[id] (хук пишет
--     в дебриф, модель кладёт тонны на склад: logistics.supply);
--   * авианаводчик (JTAC) у своего взвода в бою цели: ctld.JTACAutoLase - подсветка лазером, дым, F10 "JTAC Status".
-- Остальное CTLD (FOB, ЗРК из ящиков, маяки, техника из ящиков) выключено: в модели кампании этого нет.
REDFRONT_LIFT = REDFRONT_LIFT or {}
REDFRONT_CTLD = { pilots = {} }
local CFG = { @CFG@ }
-- pilots = { имена бортов игрока }, actions = { [тип] = {crates, troops} }, limits = { [тип] = десантников },
-- cargo = { [тип] = ящиков }, logistic = { имена машин тыла }, pickup = { {zone, side, limit} },
-- groups = { {name, inf, mg, at, aa, side} }, crates = { {weight, desc, unit, side} },
-- lifts = { {id, side, zone, title} }, jtacs = { {id, platoon, target, side, country, type, code, tx, ty, title} }

for _, n in ipairs(CFG.pilots) do REDFRONT_CTLD.pilots[n] = true end

ctld.addPlayerAircraftByType = false
ctld.transportPilotNames = CFG.pilots
ctld.unitActions = CFG.actions
ctld.unitLoadLimits = CFG.limits
ctld.internalCargoLimits = CFG.cargo
ctld.enableCrates = #CFG.crates > 0
ctld.enableAllCrates = false
ctld.slingLoad = false               -- висение над ящиком вместо физики подвески (в DCS бывают сбои)
ctld.hoverPickup = true
ctld.loadCrateFromMenu = true
ctld.dynamicCargoUnits = {}          -- ящики CTLD, не грузы DCS: их видно скрипту (подсчёт доставленного)
ctld.enabledFOBBuilding = false
ctld.enableRepackingVehicles = false
ctld.enabledRadioBeaconDrop = false
ctld.allowRandomAiTeamPickups = false
ctld.spawnRPGWithCoalition = false
ctld.spawnStinger = false
ctld.JTAC_dropEnabled = false
ctld.JTAC_jtacStatusF10 = #CFG.jtacs > 0
ctld.reconF10Menu = false
ctld.vehicleTransportEnabled = {}
ctld.extractableGroups = {}
ctld.wpZones = {}
ctld.logisticUnits = CFG.logistic
ctld.pickupZones = {}
for _, z in ipairs(CFG.pickup) do ctld.pickupZones[#ctld.pickupZones + 1] = { z.zone, "none", z.limit, "yes", z.side } end
ctld.dropOffZones = {}
for _, l in ipairs(CFG.lifts) do ctld.dropOffZones[#ctld.dropOffZones + 1] = { l.zone, "none", l.side } end
ctld.loadableGroups = CFG.groups
ctld.spawnableCrates = {}
if #CFG.crates > 0 then ctld.spawnableCrates["Supply"] = CFG.crates end

ctld.initialize()

-- меню CTLD бортам игрока: CTLD добавляет его по событию рождения, а в одиночной игре борт игрока рождается раньше
-- скриптов начала миссии (меню F10 не было) - раз в 5 с проверяем борта из списка сами
local function menus()
  for _, n in ipairs(CFG.pilots) do
    local u = Unit.getByName(n)
    if u and u:isExist() and u.getPlayerName and u:getPlayerName() and ctld.addTransportF10MenuOptions then
      pcall(ctld.addTransportF10MenuOptions, n)
    end
  end
  return timer.getTime() + 5
end
timer.scheduleFunction(menus, nil, timer.getTime() + 1)

local OURS = {}                      -- вес ящика снабжения -> да
for _, c in ipairs(CFG.crates) do OURS[tostring(c.weight)] = true end

local function inZone(name, p)
  local z = trigger.misc.getZone(name)
  if not z then return false end
  local dx, dz = p.x - z.point.x, p.z - z.point.z
  return dx * dx + dz * dz <= z.radius * z.radius
end

local unpacked = {}                  -- id перевозки -> кг, распакованные в зоне выгрузки

local function count()               -- ящики снабжения в зоне выгрузки + распакованные там
  for _, l in ipairs(CFG.lifts) do
    local kg = unpacked[l.id] or 0
    for name, c in pairs(l.side == 1 and ctld.spawnedCratesRED or ctld.spawnedCratesBLUE) do
      if c and OURS[tostring(c.weight)] then
        local s = StaticObject.getByName(name)
        if s and s:isExist() and inZone(l.zone, s:getPoint()) then kg = kg + math.floor(c.weight) end
      end
    end
    REDFRONT_LIFT[l.id] = kg
  end
  return timer.getTime() + 15
end
timer.scheduleFunction(count, nil, timer.getTime() + 15)

ctld.addCallback(function(a)
  local ok, err = pcall(function()
    if a.action == "dropped_troops" and a.unit and a.unloaded and REDFRONT_ASSAULT_CTLD then
      REDFRONT_ASSAULT_CTLD(a.unit:getName(), a.unloaded)
    elseif a.action == "unpack" and a.crate and a.unit then
      local w = (a.crate.details and a.crate.details.weight) or a.crate.weight      -- {crateUnit, dist, details}
      if not (w and OURS[tostring(w)]) then return end
      local p = a.unit:getPoint()
      for _, l in ipairs(CFG.lifts) do
        if l.side == a.unit:getCoalition() and inZone(l.zone, p) then
          unpacked[l.id] = (unpacked[l.id] or 0) + math.floor(w)
          if a.spawnedGroup and a.spawnedGroup.destroy then a.spawnedGroup:destroy() end   -- груз - на склад, не машина
          trigger.action.outTextForCoalition(l.side, "Снабжение сдано на склад: " .. l.title, 10)
          count()
          return
        end
      end
    end
  end)
  if not ok then env.error("redfront ctld: " .. tostring(err)) end
end)

-- авианаводчик: у своего взвода в бою (после battle_site.lua), на 300 м дальше от цели, невидим для ИИ противника
for _, j in ipairs(CFG.jtacs) do
  local g = Group.getByName(j.platoon)
  local u = g and g:getUnit(1)
  if u and u:isExist() then
    local p = u:getPoint()
    local tx, ty = j.tx, j.ty                 -- цель: её взвод после расстановки (battle_site.lua), иначе точка из .miz
    local tg = Group.getByName(j.target)
    local tu = tg and tg:getUnit(1)
    if tu and tu:isExist() then local tp = tu:getPoint(); tx, ty = tp.x, tp.z end
    local dx, dz = p.x - tx, p.z - ty
    local d = math.sqrt(dx * dx + dz * dz)
    if d < 1 then dx, dz, d = 1, 0, 1 end
    local x, y = p.x + 300 * dx / d, p.z + 300 * dz / d
    coalition.addGroup(j.country, Group.Category.GROUND, { name = j.id, task = {},
      units = { { name = j.id .. " #1", type = j.type, x = x, y = y, heading = (math.atan2 or math.atan)(-dz, -dx), skill = "Excellent",
                  playerCanDrive = false } } })
    local jg = Group.getByName(j.id)
    if jg then
      local c = jg:getController()
      c:setCommand({ id = "SetInvisible", params = { value = true } })
      c:setOption(AI.Option.Ground.id.ROE, AI.Option.Ground.val.ROE.WEAPON_HOLD)
      ctld.JTACAutoLase(j.id, j.code, true, "all")
      env.info("redfront ctld: авианаводчик " .. j.title)
    end
  end
end
