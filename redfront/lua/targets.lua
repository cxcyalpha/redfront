-- redfront targets | campaign @CAMPAIGN@ | sortie @SORTIE@
-- Объекты тыла (склады, мосты, аэродромы) как цели: в начале миссии ищем объекты карты (строения, мосты) в районе
-- каждого объекта (как "Assign as" в редакторе). Их гибель хук запишет в файл дебрифа (REDFRONT_TARGET_OF), модель
-- переведёт в повреждение объекта. Статика складов (если поставлена генератором) учитывается хуком как обычно.
REDFRONT_TARGETS = REDFRONT_TARGETS or {}
REDFRONT_TARGET_OF = REDFRONT_TARGET_OF or {}

local OBJECTS = { @OBJECTS@ }

-- Мост: если зонд карты дал имена его пролётов (names) - только они. Иначе только объекты карты, чей тип похож на
-- мост (bridge/most, в редакторе мосты - rw_bridge_2line и т.п.); если таких нет - один ближайший к точке
-- объект (точка неточная - это будет дом, поэтому в журнал DCS пишется предупреждение и типы найденного).
local function isBridge(t) t = string.lower(t or ""); return t:find("bridge") or t:find("most") end

for _, o in ipairs(OBJECTS) do
  local found = {}
  local ok = pcall(function()
    local vol = { id = world.VolumeType.SPHERE,
                  params = { point = { x = o.x, y = land.getHeight({ x = o.x, y = o.y }), z = o.y }, radius = o.r } }
    world.searchObjects(Object.Category.SCENERY, vol, function(obj)
      local okn, nm = pcall(function() return obj:getName() end)
      nm = okn and nm ~= nil and tostring(nm) or nil      -- имя объекта карты - число; в names (зонд) и в хуке - строка
      local okt, tp = pcall(function() return obj:getTypeName() end)
      local okp, p = pcall(function() return obj:getPoint() end)
      if nm and not REDFRONT_TARGET_OF[nm] then
        local d = okp and math.sqrt((p.x - o.x) ^ 2 + (p.z - o.y) ^ 2) or o.r
        found[#found + 1] = { name = nm, type = okt and tp or "?", d = d }
      end
      return true
    end)
  end)
  table.sort(found, function(a, b) return a.d < b.d end)
  local pick, note = {}, ""
  if next(o.names or {}) then             -- мост уточнён зондом карты (map-apply): только его пролёты по именам
    for _, f in ipairs(found) do if o.names[f.name] then pick[#pick + 1] = f end end
    if #pick == 0 then note = " ВНИМАНИЕ: пролёты моста по именам не найдены" end
  elseif o.role == "bridge" then
    for _, f in ipairs(found) do if isBridge(f.type) then pick[#pick + 1] = f end end
    if #pick == 0 and #found > 0 then
      pick = { found[1] }
      note = " ВНИМАНИЕ: мостов рядом нет, взят ближайший объект - проверьте координаты (set-pos)"
    end
  else
    pick = found
  end
  local n, types = 0, {}
  for _, f in ipairs(pick) do
    if n < o.max then
      n = n + 1
      REDFRONT_TARGET_OF[f.name] = o.id
      types[#types + 1] = string.format("%s %.0fм", f.type, f.d)
    end
  end
  REDFRONT_TARGETS[o.id] = { n = n, ok = ok }
  env.info(string.format("redfront targets %s: объектов карты %d (в радиусе %d): %s%s", o.id, n, #found,
                         table.concat(types, ", "), note))
end
