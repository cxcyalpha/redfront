-- redfront airbase probe | theatre @THEATRE@
-- Служебная миссия: все аэродромы и площадки карты (world.getAirbases) - id, имя, место, полосы, стоянки - в
-- <Saved Games>\DCS...\redfront\airbases_@THEATRE@.json. Нужна, когда карта DCS обновилась (новые аэродромы), а
-- pydcs их ещё не знает: redfront добавит недостающие (airbases_ext.py). Летать не нужно: дождаться сообщения и выйти.
-- ТРЕБУЕТ: io и lfs не "санитизированы" в <DCS>\Scripts\MissionScripting.lua.
if not (io and lfs) then
  trigger.action.outText("redfront: аэродромы не сохранятся - MissionScripting.lua не разблокирован", 60)
  return
end
local DIR = lfs.writedir() .. "redfront"
lfs.mkdir(DIR)
local OUT = DIR .. "\\airbases_@THEATRE@.json"

local function esc(s)
  return (tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", string.byte(c)) end))
end

local items, errors = {}, {}
for _, ab in ipairs(world.getAirbases() or {}) do
  local ok, err = pcall(function()
    local d = ab:getDesc() or {}
    local p = ab:getPoint()
    local rws, slots = {}, {}
    local okr, runways = pcall(function() return ab:getRunways() end)
    for _, r in ipairs(okr and runways or {}) do
      rws[#rws + 1] = string.format('{"name":"%s","course":%.4f,"length":%.0f,"width":%.0f,"x":%.1f,"y":%.1f}',
        esc(r.Name or ""), r.course or 0, r.length or 0, r.width or 0, r.position and r.position.x or 0,
        r.position and r.position.z or 0)
    end
    local okp, parking = pcall(function() return ab:getParking() end)
    for _, s in ipairs(okp and parking or {}) do
      local v = s.vTerminalPos or {}
      slots[#slots + 1] = string.format('{"idx":%d,"type":%d,"x":%.2f,"y":%.2f,"rw":%.0f}',
        s.Term_Index or 0, s.Term_Type or 0, v.x or 0, v.z or 0, s.fDistToRW or 0)
    end
    items[#items + 1] = string.format('{"id":%d,"name":"%s","callsign":"%s","category":%d,"x":%.2f,"y":%.2f,"alt":%.1f,'
      .. '"runways":[%s],"parking":[%s]}', tonumber(ab:getID()) or -1, esc(ab:getName()), esc(ab:getCallsign() or ""),
      d.category or -1, p.x, p.z, p.y, table.concat(rws, ","), table.concat(slots, ","))
  end)
  if not ok then errors[#errors + 1] = '"' .. esc(err) .. '"' end
end
local f = io.open(OUT, "w")
f:write(string.format('{"theatre":"@THEATRE@","map":"%s","airbases":[%s],"errors":[%s]}',
  esc(env.mission and env.mission.theatre or "?"), table.concat(items, ","), table.concat(errors, ",")))
f:close()
trigger.action.outText(string.format("redfront: аэродромы записаны (%d) - %s. Можно выйти.", #items, OUT), 120)
