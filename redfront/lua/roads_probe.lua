-- redfront roads probe | sector @SECTOR@
-- Служебная миссия: спрашивает у DCS путь по дорогам между соседними пунктами маршрутов и пишет его в
-- <Saved Games>\DCS...\redfront\roads_@SECTOR@.json. Летать не нужно: дождаться сообщения и выйти.
-- ТРЕБУЕТ: io и lfs не "санитизированы" в <DCS>\Scripts\MissionScripting.lua.
if not (io and lfs) then
  trigger.action.outText("redfront: дороги не сохранятся - MissionScripting.lua не разблокирован", 60)
  return
end
local DIR = lfs.writedir() .. "redfront"
lfs.mkdir(DIR)
local OUT = DIR .. "\\roads_@SECTOR@.json"
local PAIRS = { @PAIRS@ }        -- { id = "A>B", x1, y1, x2, y2 } в координатах карты DCS (x - север, y - восток)

local function esc(s)
  return (tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", string.byte(c)) end))
end
-- API возвращает точку либо двумя числами, либо таблицей {x=, y=}: принимаем оба вида
local function xy(a, b)
  if type(a) == "table" then return a.x, a.y end
  return a, b
end

local paths, errors = {}, {}
for _, p in ipairs(PAIRS) do
  local ok, err = pcall(function()
    local ax, ay = xy(land.getClosestPointOnRoads("roads", p.x1, p.y1))
    local bx, by = xy(land.getClosestPointOnRoads("roads", p.x2, p.y2))
    if not (ax and bx) then error("нет ближайшей точки на дороге") end
    local path = land.findPathOnRoads("roads", ax, ay, bx, by)
    if type(path) ~= "table" or #path < 2 then error("путь по дорогам не найден") end
    local pts = {}
    for _, q in ipairs(path) do
      local x, y = xy(q)
      pts[#pts + 1] = string.format("[%.1f,%.1f]", x, y)
    end
    paths[#paths + 1] = string.format('"%s":[%s]', esc(p.id), table.concat(pts, ","))
  end)
  if not ok then errors[#errors + 1] = string.format('"%s":"%s"', esc(p.id), esc(err)) end
end

local f = io.open(OUT, "w")
if f then
  f:write(string.format('{"sector":"@SECTOR@","paths":{%s},"errors":{%s}}', table.concat(paths, ","), table.concat(errors, ",")))
  f:close()
  trigger.action.outText(string.format("redfront: дороги записаны (%d путей, %d ошибок) в %s. Можно выходить.",
    #paths, #errors, OUT), 120)
else
  trigger.action.outText("redfront: не удалось открыть файл " .. OUT, 120)
end
