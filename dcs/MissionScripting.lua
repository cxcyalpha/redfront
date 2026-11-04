--Initialization script for the Mission lua Environment (SSE)

dofile('Scripts/ScriptingSystem.lua')

--Sanitize Mission Scripting environment
--This makes unavailable some unsecure functions.
--Mission downloaded from server to client may contain potentialy harmful lua code that may use these functions.
--You can remove the code below and make availble these functions at your own risk.

-- redfront: io и lfs открыты - хук дебрифа (debrief_hook.lua) пишет итог миссии в Saved Games\DCS\redfront\.
-- Риск: миссии с чужих серверов тоже получат доступ к файлам. os, require, loadlib, package - закрыты, как в DCS.
-- Обновление DCS возвращает свой файл - положите этот снова.

local function sanitizeModule(name)
	_G[name] = nil
	package.loaded[name] = nil
end

do
	sanitizeModule('os')
	--sanitizeModule('io')
	--sanitizeModule('lfs')
	_G['require'] = nil
	_G['loadlib'] = nil
	_G['package'] = nil
end
