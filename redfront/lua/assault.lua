-- redfront assault | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Вертолётный десант. Рота стоит в .miz на площадке с поздней активацией. Раз в CHECK_S секунд скрипт смотрит
-- вертолёты десантной группы: борт на земле (не в воздухе) ближе r метров к площадке - сел; первая посадка
-- выпускает роту (Group.activate) и пишет сообщение. Сколько бортов село из скольких - REDFRONT_ASSAULT[id]
-- (хук дебрифа пишет в файл; модель по нему решает, удалась ли высадка, assault.py).
REDFRONT_ASSAULT = REDFRONT_ASSAULT or {}
local CHECK_S = 3
local SPECS = { @SPECS@ }

local function check()
  local again = false
  for _, s in ipairs(SPECS) do
    local st = REDFRONT_ASSAULT[s.id]
    if not st then
      st = { landed = 0, total = #s.helos, seen = {}, out = false }
      REDFRONT_ASSAULT[s.id] = st
    end
    for _, n in ipairs(s.helos) do
      if not st.seen[n] then
        local u = Unit.getByName(n)
        if u and u:isExist() and not u:inAir() then
          local p = u:getPoint()
          local dx, dz = p.x - s.x, p.z - s.y
          if dx * dx + dz * dz <= s.r * s.r then
            st.seen[n] = true
            st.landed = st.landed + 1
            if not st.out then
              local g = Group.getByName(s.troops)
              if g then g:activate() end
              st.out = true
              trigger.action.outText("Десант высажен: " .. s.title, 15)
            end
          end
        end
      end
    end
    if st.landed < st.total then again = true end
  end
  if again then return timer.getTime() + CHECK_S end
  return nil
end

timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
