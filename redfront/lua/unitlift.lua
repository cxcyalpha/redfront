-- redfront unitlift | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Вертолётом к части (снабжение, вывоз раненых) - игрок: сесть у части на площадку (дым) и простоять land с;
--   * снабжение: груз сдан - рейс засчитан;
--   * вывоз раненых: раненые на борту - доставить на свой аэродром (сесть у него), тогда рейс засчитан.
-- Борта ИИ - по модели (не сбит - рейс выполнен). REDFRONT_ULIFT[id] = { done = 0/1 }.
REDFRONT_ULIFT = REDFRONT_ULIFT or {}
local CHECK_S = 3
local BASE_R = 2000
local SPECS = { @SPECS@ }   -- { id, mode, title, x, y, r, land, helos = {...} }

local function dist(x1, y1, x2, y2) local dx, dy = x1 - x2, y1 - y2; return math.sqrt(dx * dx + dy * dy) end
local function isPlayer(u) return u and u.getPlayerName and u:getPlayerName() ~= nil end
local function msg(u, text, t) trigger.action.outTextForGroup(u:getGroup():getID(), text, t or 10) end
local stay, aboard, told = {}, {}, {}

for _, s in ipairs(SPECS) do
  REDFRONT_ULIFT[s.id] = { done = 0 }
  trigger.action.smoke({ x = s.x, y = land.getHeight({ x = s.x, y = s.y }), z = s.y }, trigger.smokeColor.Green)
end

local function nearOwnBase(u)
  local p = u:getPoint()
  for _, b in ipairs(coalition.getAirbases(u:getCoalition()) or {}) do
    local bp = b:getPoint()
    if dist(p.x, p.z, bp.x, bp.z) <= BASE_R then return true end
  end
  return false
end

local function check()
  for _, s in ipairs(SPECS) do
    for _, n in ipairs(s.helos) do
      local u = Unit.getByName(n)
      if u and u:isExist() and isPlayer(u) and REDFRONT_ULIFT[s.id].done == 0 then
        local p = u:getPoint()
        local d = dist(p.x, p.z, s.x, s.y)
        if not told[n] and d < 3000 then
          told[n] = true
          msg(u, s.title .. ": площадка - зелёный дым. Сядьте и ждите " .. s.land .. " с.", 15)
        end
        if aboard[n] then
          if not u:inAir() and nearOwnBase(u) then
            REDFRONT_ULIFT[s.id].done = 1
            msg(u, "Раненые доставлены. Рейс засчитан.", 15)
          end
        elseif not u:inAir() and d <= s.r then
          stay[n] = (stay[n] or 0) + CHECK_S
          if stay[n] >= s.land then
            if s.mode == "medevac" then
              aboard[n] = true
              msg(u, "Раненые на борту - на свой аэродром.", 15)
            else
              REDFRONT_ULIFT[s.id].done = 1
              msg(u, "Груз сдан части. Рейс засчитан.", 15)
            end
          elseif stay[n] % 15 < CHECK_S then
            msg(u, (s.mode == "medevac" and "Погрузка раненых: ещё " or "Разгрузка: ещё ") .. (s.land - stay[n]) .. " с.", 3)
          end
        else
          stay[n] = 0
        end
      end
    end
  end
  return timer.getTime() + CHECK_S
end
timer.scheduleFunction(check, nil, timer.getTime() + CHECK_S)
