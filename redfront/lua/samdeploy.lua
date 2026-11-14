-- redfront samdeploy | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Развёртывание ЗРК с марша (ОЦЕНКИ времени - build.SAM_DEPLOY_S): ЗРК в колонне с ходу не стреляет; после
-- остановки - только через время развёртывания своего типа (минуты). Пока группа движется - огонь запрещён
-- (ROE WEAPON_HOLD), стоит не меньше deploy секунд - огонь разрешён (OPEN_FIRE); тронулась - снова запрещён.
-- Зенитные пушки (Шилка, Gepard, ЗУ) стреляют с ходу - в список не входят. Итог - REDFRONT_SAMDEPLOY.events.
REDFRONT_SAMDEPLOY = REDFRONT_SAMDEPLOY or { events = {} }
local SPECS = { @SPECS@ }   -- { group = имя группы, deploy = секунд }
local MOVING = 1.0          -- м/с: быстрее - группа на марше
local ROE = AI.Option.Ground.id.ROE
local HOLD = AI.Option.Ground.val.ROE.WEAPON_HOLD
local OPEN = AI.Option.Ground.val.ROE.OPEN_FIRE
local st = {}

local function speed(g)
  local mx = 0
  for _, u in ipairs(g:getUnits() or {}) do
    local ok, v = pcall(function() return u:getVelocity() end)
    if ok and v then
      local s = math.sqrt(v.x * v.x + v.z * v.z)
      if s > mx then mx = s end
    end
  end
  return mx
end

local function set(g, s, mode, t)
  local x = st[s.group]
  if x.mode == mode then return end
  x.mode = mode
  pcall(function() g:getController():setOption(ROE, mode == "free" and OPEN or HOLD) end)
  table.insert(REDFRONT_SAMDEPLOY.events, { group = s.group, mode = mode, t = t })
end

local function tick(_, t)
  for _, s in ipairs(SPECS) do
    local g = Group.getByName(s.group)
    if g and g:isExist() then
      st[s.group] = st[s.group] or {}
      local x = st[s.group]
      if speed(g) > MOVING then
        x.stop = nil
        set(g, s, "hold", t)
      else
        x.stop = x.stop or t
        if t - x.stop >= s.deploy then set(g, s, "free", t) else set(g, s, "hold", t) end
      end
    end
  end
  return t + 2
end

timer.scheduleFunction(tick, nil, timer.getTime() + 1)
