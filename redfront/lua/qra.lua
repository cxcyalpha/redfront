-- redfront qra | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Дежурные звенья ПВО. Звено стоит на стоянке своего аэродрома с запущенными двигателями (поздняя активация: до
-- тревоги его в мире DCS нет). Раз в CHECK_S секунд - налёты по картине наземных РЛС стороны (airpic.lua): самолёты
-- противника, идущие к своим объектам; вертолёты и уходящие цели тревоги не поднимают. Подъём соразмерный: на налёт
-- из n самолётов - ceil(n / per_flight) звеньев (не больше max_per_raid), уже поднятые и живые звенья засчитываются;
-- reserve звеньев стороны остаются на земле (кроме звена, к чьей базе налёт ближе base_km). Поднимается звено,
-- ближнее к налёту (база ближе r). Дальше его ведёт задача из .miz и наведение (gci.lua). Кто и когда поднят -
-- REDFRONT_QRA (хук пишет в дебриф). Все величины - ОЦЕНКИ доктрины (qra: per_flight, max_per_raid, reserve, base_km).
REDFRONT_QRA = REDFRONT_QRA or {}
local CHECK_S = 10
local SPECS = { @SPECS@ }          -- { id, group, side, x, y, r, title }
local SIDES = { @SIDES@ }          -- [сторона] = { per_flight, max_per_raid, reserve, base_km }

local function alive(s)
  local g = Group.getByName(s.group)
  if not g or not g:isExist() then return false end
  for _, u in ipairs(g:getUnits() or {}) do if u and u:isExist() then return true end end
  return false
end

local function dist(s, p) return math.sqrt((s.x - p.x) ^ 2 + (s.y - p.z) ^ 2) end

local function check()
  local left = false
  for side, prm in pairs(SIDES) do
    local ground, up = {}, 0
    for _, s in ipairs(SPECS) do
      if s.side == side then
        if REDFRONT_QRA[s.id] then
          if alive(s) then up = up + 1 end
        else
          ground[#ground + 1] = s
        end
      end
    end
    if #ground > 0 then
      left = true
      local need, raids = 0, RF_AIR.raids(side, false, true)
      table.sort(raids, function(a, b) return a.n > b.n end)
      for _, r in ipairs(raids) do need = need + math.min(prm.max_per_raid, math.ceil(r.n / prm.per_flight)) end
      for _, r in ipairs(raids) do                -- крупные налёты - первыми; на налёт - до своей доли звеньев
        local want = math.min(prm.max_per_raid, math.ceil(r.n / prm.per_flight))
        for _ = 1, want do
          if up >= need then break end
          local best, bd
          for _, s in ipairs(ground) do
            local d = dist(s, r.pos)
            local spare = #ground > prm.reserve or d <= prm.base_km   -- резерв - на земле, если налёт не на его базу
            if d <= s.r and spare and (not bd or d < bd) then best, bd = s, d end
          end
          if not best then break end
          local g = Group.getByName(best.group)
          if g then g:activate() end
          REDFRONT_QRA[best.id] = math.floor(timer.getTime())
          up = up + 1
          for k, s in ipairs(ground) do if s == best then table.remove(ground, k); break end end
          env.info("redfront qra: " .. best.title .. " - взлёт по налёту " .. r.n .. " x " .. r.lead:getTypeName()
                   .. " (" .. math.floor(bd / 1000) .. " км)")
        end
      end
    end
  end
  if left then return timer.getTime() + CHECK_S end
  return nil
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
