
-- AERO = single ejector
-- If TER or MER loadout not specified (e.g. 101 or 010010), assume full TER/MER loaded

A6_SHARED_weapons =
{
	-- Racks
	{id = "{HB_A6E_TER}", pylons = {1,1,1,1,1}}, -- TER EMPTY
	{id = "{HB_A6E_MER}", pylons = {1,1,1,1,1}}, -- MER EMPTY

	-- Practice Bombs
	{id = "{HB_A6E_BDU33_TER_3x}",	pylons = {1,1,1,1,1}}, -- BDU-33 TER
	{id = "{HB_A6E_BDU33_MER_6x}",	pylons = {1,1,1,1,1}}, -- BDU-33 MER
	{id = "{HB_A6E_MK76_TER_3x}",	pylons = {1,1,1,1,1}}, -- Mk76 TER
	{id = "", pylons = {1,1,1,1,1}}, -- BDU-48 TER
	{id = "", pylons = {1,1,1,1,1}}, -- BDU-48 MER
	{id = "{HB_A6E_MK106_TER_3x}",	pylons = {1,1,1,1,1}}, -- Mk106mod5 TER
	{id = "{HB_A6E_MK106_MER_6x}",	pylons = {1,1,1,1,1}}, -- Mk106mod5 MER

	{id = "{BDU_45B}",						pylons = {1,1,1,1,1}}, -- BDU-45 AERO
	{id = "{HB_A6E_BDU45_TER_3x}",			pylons = {1,1,1,1,1}}, -- BDU-45 TER
	{id = "{HB_A6E_BDU45_TER_2x_RIGHT}",	pylons = {1,1,0,1,1}}, -- BDU-45 TER 011
	{id = "{HB_A6E_BDU45_MER_6x}",			pylons = {1,0,1,0,1}}, -- BDU-45 MER
	{id = "{HB_A6E_BDU45_MER_5x_RIGHT}",	pylons = {0,1,0,1,0}}, -- BDU-45 MER 011111
	{id = "{HB_A6E_BDU45_MER_4x_RIGHT}",	pylons = {1,1,0,1,1}}, -- BDU-45 MER 011011
	{id = "{HB_A6E_BDU45_MER_3x_RIGHT}",	pylons = {1,1,0,1,1}}, -- BDU-45 MER 011010
	{id = "{HB_A6E_BDU45_MER_2x}",			pylons = {1,1,0,1,1}}, -- BDU-45 MER 010010
	{id = "{HB_A6E_BDU45_MER_1x}",			pylons = {1,1,0,1,1}}, -- BDU-45 MER 010000

	{id = "{BDU_45}",						pylons = {1,1,1,1,1}}, -- BDU-45SE AERO
	{id = "{HB_A6E_BDU45SE_TER_3x}",		pylons = {1,0,1,0,1}}, -- BDU-45SE TER
	{id = "{HB_A6E_BDU45SE_TER_2x_RIGHT}",	pylons = {1,1,0,1,1}}, -- BDU-45SE TER 011
	{id = "{HB_A6E_BDU45SE_MER_6x}",		pylons = {1,0,0,0,1}}, -- BDU-45SE MER
	{id = "{HB_A6E_BDU45SE_MER_5x}",		pylons = {0,0,1,0,0}}, -- BDU-45SE MER 111101
	{id = "{HB_A6E_BDU45SE_MER_5x_RIGHT}",	pylons = {0,1,0,1,0}}, -- BDU-45SE MER 011111
	{id = "{HB_A6E_BDU45SE_MER_4x_RIGHT}",	pylons = {1,1,0,1,1}}, -- BDU-45SE MER 011011
	{id = "{HB_A6E_BDU45SE_MER_3x_RIGHT}",	pylons = {1,1,0,1,1}}, -- BDU-45SE MER 011010
	{id = "{HB_A6E_BDU45SE_MER_2x}",		pylons = {1,1,0,1,1}}, -- BDU-45SE MER 010010
	{id = "{HB_A6E_BDU45SE_MER_1x}",		pylons = {1,1,0,1,1}}, -- BDU-45SE MER 010000

	-- Incendiary Bombs
	{id = "", pylons = {1,1,1,1,1}}, -- CBU-72 AERO
	{id = "", pylons = {1,1,0,1,1}}, -- CBU-72 TER 011
	{id = "", pylons = {0,0,1,0,0}}, -- CBU-72 TER 101
	{id = "", pylons = {1,1,0,1,1}}, -- CBU-72 MER 011011
	{id = "", pylons = {1,1,1,1,1}}, -- Mk77 AERO
	{id = "", pylons = {1,1,1,1,1}}, -- Mk77 TER 010
	{id = "", pylons = {1,1,1,1,1}}, -- Mk77 MER 010010

	-- HE Bombs and Bomb Mines
	{id = "{90321C8E-7ED1-47D4-A160-E074D5ABD902}", pylons = {1,1,1,1,1}}, -- Mk81 AERO
	{id = "{HB_A6E_MK81_TER_3x}",					pylons = {1,1,1,1,1}}, -- Mk81 TER
	{id = "{HB_A6E_MK81_TER_2x_RIGHT}",				pylons = {1,1,0,1,1}}, -- Mk81 TER 011
	{id = "{HB_A6E_MK81_MER_6x}",					pylons = {1,0,1,0,1}}, -- Mk81 MER
	{id = "{HB_A6E_MK81_MER_5x_RIGHT}",				pylons = {0,1,0,1,0}}, -- Mk81 MER 011111
	{id = "{HB_A6E_MK81_MER_4x_RIGHT}",				pylons = {1,1,0,1,1}}, -- Mk81 MER 011011
	{id = "{HB_A6E_MK81_MER_3x_RIGHT}",				pylons = {1,1,0,1,1}}, -- Mk81 MER 011010
	{id = "{HB_A6E_MK81_MER_2x}",					pylons = {1,1,0,1,1}}, -- Mk81 MER 010010
	{id = "{HB_A6E_MK81_MER_1x}",					pylons = {1,1,0,1,1}}, -- Mk81 MER 010000

	{id = "", pylons = {1,1,1,1,1}}, -- Mk81SE AERO
	{id = "", pylons = {1,1,1,1,1}}, -- Mk81SE TER
	{id = "", pylons = {1,1,0,1,1}}, -- Mk81SE TER 011
	{id = "", pylons = {1,0,1,0,1}}, -- Mk81SE MER
	{id = "", pylons = {0,1,0,1,0}}, -- Mk81SE MER 011111
	{id = "", pylons = {1,1,0,1,1}}, -- Mk81SE MER 011011

	{id = "{BCE4E030-38E9-423E-98ED-24BE3DA87C32}", pylons = {1,1,1,1,1}}, -- Mk82 AERO
	{id = "{HB_A6E_MK82_TER_3x}",					pylons = {1,1,1,1,1}}, -- Mk82 TER
	{id = "{HB_A6E_MK82_TER_2x_RIGHT}", 			pylons = {1,1,0,1,1}}, -- Mk82 TER 011
	{id = "{HB_A6E_MK82_MER_6x}",					pylons = {1,0,1,0,1}}, -- Mk82 MER
	{id = "{HB_A6E_MK82_MER_5x_RIGHT}",				pylons = {0,1,0,1,0}}, -- Mk82 MER 011111
	{id = "{HB_A6E_MK82_MER_4x_RIGHT}",				pylons = {1,1,0,1,1}}, -- Mk82 MER 011011
	{id = "{HB_A6E_MK82_MER_3x_RIGHT}",				pylons = {1,1,0,1,1}}, -- Mk82 MER 011010
	{id = "{HB_A6E_MK82_MER_2x}",					pylons = {1,1,0,1,1}}, -- Mk82 MER 010010
	{id = "{HB_A6E_MK82_MER_1x}",					pylons = {1,1,0,1,1}}, -- Mk82 MER 010000

	{id = "{Mk82SNAKEYE}",					pylons = {1,1,1,1,1}}, -- Mk82SE AERO
	{id = "{HB_A6E_MK82SE_TER_3x}",			pylons = {1,0,1,0,1}}, -- Mk82SE TER
	{id = "{HB_A6E_MK82SE_TER_2x_RIGHT}",	pylons = {1,1,0,1,1}}, -- Mk82SE TER 011
	{id = "{HB_A6E_MK82SE_MER_6x}",			pylons = {1,0,0,0,1}}, -- Mk82SE MER
	{id = "{HB_A6E_MK82SE_MER_5x_RIGHT}",	pylons = {0,1,0,1,0}}, -- Mk82SE MER 011111
	{id = "{HB_A6E_MK82SE_MER_4x_RIGHT}",	pylons = {1,1,0,1,1}}, -- Mk82SE MER 011011
	{id = "{HB_A6E_MK82SE_MER_5x}",			pylons = {0,0,1,0,0}}, -- Mk82SE MER 111101
	{id = "{HB_A6E_MK82SE_MER_3x_RIGHT}",	pylons = {1,1,0,1,1}}, -- Mk82SE MER 011010
	{id = "{HB_A6E_MK82SE_MER_2x}",			pylons = {1,1,0,1,1}}, -- Mk82SE MER 010010
	{id = "{HB_A6E_MK82SE_MER_1x}",			pylons = {1,1,0,1,1}}, -- Mk82SE MER 010000

	{id = "", pylons = {1,1,1,1,1}}, -- Mk36DST AERO
	{id = "", pylons = {1,0,1,0,1}}, -- Mk36DST TER
	{id = "", pylons = {1,1,0,1,1}}, -- Mk36DST TER 011
	{id = "", pylons = {1,0,0,0,1}}, -- Mk36DST MER
	{id = "", pylons = {0,1,0,1,0}}, -- Mk36DST MER 011111
	{id = "", pylons = {1,1,0,1,1}}, -- Mk36DST MER 011011
	{id = "", pylons = {0,0,1,0,0}}, -- Mk36DST MER 111101

	{id = "", pylons = {1,1,1,1,1}}, -- Mk62 QUICKSTRIKE AERO
	{id = "", pylons = {1,0,1,0,1}}, -- Mk62 QUICKSTRIKE TER
	{id = "", pylons = {1,1,0,1,1}}, -- Mk62 QUICKSTRIKE TER 011
	{id = "", pylons = {1,0,0,0,1}}, -- Mk62 QUICKSTRIKE MER
	{id = "", pylons = {0,1,0,1,0}}, -- Mk62 QUICKSTRIKE MER 011111
	{id = "", pylons = {1,1,0,1,1}}, -- Mk62 QUICKSTRIKE MER 011011
	{id = "", pylons = {0,0,1,0,0}}, -- Mk62 QUICKSTRIKE MER 111101

	{id = "{7A44FF09-527C-4B7E-B42B-3F111CFE50FB}", pylons = {1,1,1,1,1}}, -- Mk83 AERO
	{id = "{HB_A6E_MK83_TER_3x}",					pylons = {1,0,1,0,1}}, -- Mk83 TER
	{id = "{HB_A6E_MK83_TER_2x_RIGHT}", 			pylons = {1,1,0,1,1}}, -- Mk83 TER 011
	{id = "{HB_A6E_MK83_MER_3x_FWD}",				pylons = {1,0,1,0,1}}, -- Mk83 MER 101010
	{id = "{HB_A6E_MK83_MER_3x_AFT}",				pylons = {0,1,0,1,0}}, -- Mk83 MER 010101
	{id = "{HB_A6E_MK83_MER_2x_RIGHT}",				pylons = {1,1,0,1,1}}, -- Mk83 MER 001010
	{id = "{HB_A6E_MK83_MER_1x}",					pylons = {1,1,0,1,1}}, -- Mk83 MER 010000

	{id = "", pylons = {1,1,1,1,1}}, -- Mk83SE AERO
	{id = "", pylons = {1,0,1,0,1}}, -- Mk83SE TER 101
	{id = "", pylons = {1,1,0,1,1}}, -- Mk83SE MER 001010
	{id = "", pylons = {0,0,1,0,0}}, -- Mk83SE MER 010100 -- Not sure about this one, check with SMEs

	{id = "", pylons = {1,1,1,1,1}}, -- Mk40DST AERO
	{id = "", pylons = {1,0,1,0,1}}, -- Mk40DST TER 101
	{id = "", pylons = {1,1,0,1,1}}, -- Mk40DST MER 001010
	{id = "", pylons = {0,0,1,0,0}}, -- Mk40DST MER 010100 -- Not sure about this one, check with SMEs

	{id = "", pylons = {1,1,1,1,1}}, -- Mk63 QUICKSTRIKE AERO
	{id = "", pylons = {1,0,1,0,1}}, -- Mk63 QUICKSTRIKE TER 101
	{id = "", pylons = {1,1,0,1,1}}, -- Mk63 QUICKSTRIKE MER 001010
	{id = "", pylons = {0,0,1,0,0}}, -- Mk63 QUICKSTRIKE MER 010100 -- Not sure about this one, check with SMEs

	-- Ignoring MAU-91 fin options as I don't see enough difference between MAU-91 and Mk12 for SE bombs

	{id = "", pylons = {1,1,1,1,1}}, -- Mk83Y AERO
	{id = "", pylons = {1,0,1,0,1}}, -- Mk83Y TER 101
	{id = "", pylons = {1,0,1,0,1}}, -- Mk83Y MER 101010
	{id = "", pylons = {0,1,0,1,0}}, -- Mk83Y MER 010101

	{id = "{AB8B8299-F1CC-4359-89B5-2172E0CF4A5A}", pylons = {1,1,1,1,1}}, -- Mk84 AERO

	{id = "", pylons = {1,1,1,1,1}}, -- Mk84SE AERO

	{id = "", pylons = {1,1,1,1,1}}, -- Mk41DST AERO

	{id = "", pylons = {1,1,1,1,1}}, -- Mk64 QUICKSTRIKE AERO

	{id = "{00F5DAC4-0466-4122-998F-B1A298E34113}",	pylons = {1,1,1,1,1}}, -- M1117D AERO
	{id = "{HB_A6E_M117_TER_3x}",					pylons = {1,0,1,0,1}}, -- M1117D TER 111
	{id = "{HB_A6E_M117_TER_2x_RIGHT}",				pylons = {0,1,0,1,0}}, -- M1117D TER 011
	{id = "{HB_A6E_M117_MER_4x}",					pylons = {1,0,1,0,1}}, -- M1117D MER 101101
	{id = "{HB_A6E_M117_MER_4x_RIGHT}",				pylons = {1,1,0,1,1}}, -- M1117D MER 011011

	-- Laser Guided Bombs
	{id = "{DB769D48-67D7-42ED-A2BE-108D566C8B1E}", pylons = {1,1,0,1,1}}, -- GBU-12 AERO
	{id = "{HB_A6E_GBU12_TER_2x}",					pylons = {1,0,0,0,1}}, -- GBU-12 TER 101
	{id = "{HB_A6E_GBU12_TER_1x}",					pylons = {0,1,1,1,0}}, -- GBU-12 TER 010
	{id = "{HB_A6E_GBU12_MER_2x_RIGHT}",			pylons = {1,1,0,1,1}}, -- GBU-12 MER 001010

	{id = "{0D33DDAE-524F-4A4E-B5B8-621754FE3ADE}", pylons = {1,1,0,1,1}}, -- GBU-16 AERO
	{id = "{HB_A6E_GBU16_TER_1x}",					pylons = {1,1,1,1,1}}, -- GBU-16 TER 010
	{id = "{HB_A6E_GBU16_MER_1x_AFT}",				pylons = {1,0,1,0,1}}, -- GBU-16 MER 000010
	{id = "{HB_A6E_GBU16_MER_1x_FWD}",				pylons = {0,1,0,1,0}}, -- GBU-16 MER 010000

	{id = "{51F9AAE5-964F-4D21-83FB-502E3BFE5F8A}", pylons = {1,1,0,1,1}}, -- GBU-10 AERO

	-- Rockets
	-- 4 shot Zuni
	{id = "{F3EFE0AB-E91A-42D8-9CA2-B63C91ED570A}", pylons = {1,1,0,1,1}}, -- LAU10 ZUNI MK32 AERO
	{id = "{HB_A6E_LAU10_TER_3x}",					pylons = {1,0,0,0,1}}, -- LAU10 ZUNI MK32 TER
	{id = "{HB_A6E_LAU10_TER_2x_RIGHT}",			pylons = {0,1,0,1,0}}, -- LAU10  ZUNI MK32TER 011

	-- 19 shot 2.75
	{id = "", pylons = {1,1,0,1,1}}, -- LAU61 MK5 AERO
	{id = "", pylons = {1,0,0,0,1}}, -- LAU61 MK5 TER
	{id = "", pylons = {0,1,0,1,0}}, -- LAU61 MK5 TER 011

	{id = "{FD90A1DC-9147-49FA-BF56-CB83EF0BD32B}",	pylons = {1,1,0,1,1}}, -- LAU61 MK151 AERO
	{id = "{HB_A6E_LAU61MK151_TER_3x}",				pylons = {1,0,0,0,1}}, -- LAU61 MK151 TER
	{id = "{HB_A6E_LAU61MK151_TER_2x_RIGHT}",		pylons = {0,1,0,1,0}}, -- LAU61 MK151 TER 011

	-- 7 shot 2.75
	{id = "{174C6E6D-0C3D-42ff-BCB3-0853CB371F5C}",	pylons = {1,1,0,1,1}}, -- LAU68 MK5 AERO
	{id = "{HB_A6E_LAU68MK5_TER_3x}",				pylons = {1,0,0,0,1}}, -- LAU68 MK5 TER
	{id = "{HB_A6E_LAU68MK5_TER_2x_RIGHT}",			pylons = {0,1,0,1,0}}, -- LAU68 MK5 TER 011

	{id = "{A021F29D-18AB-4d3e-985C-FC9C60E35E9E}", pylons = {1,1,0,1,1}}, -- LAU68 MK151 AERO
	{id = "{HB_A6E_LAU68MK151_TER_3x}",				pylons = {1,0,0,0,1}}, -- LAU68 MK151 TER
	{id = "{HB_A6E_LAU68MK151_TER_2x_RIGHT}",		pylons = {0,1,0,1,0}}, -- LAU68 MK151 TER 011

	-- Cluster Bombs
	{id = "{ADD3FAE1-EBF6-4EF9-8EFC-B36B5DDF1E6B}",	pylons = {1,1,1,1,1}}, -- ROCKEYE AERO
	{id = "{HB_A6E_MK20_TER_3x}",					pylons = {1,0,1,0,1}}, -- ROCKEYE TER
	{id = "{HB_A6E_MK20_TER_2x_RIGHT}",				pylons = {0,1,0,1,0}}, -- ROCKEYE TER 011
	{id = "{HB_A6E_MK20_MER_6x}",					pylons = {1,0,1,0,1}}, -- ROCKEYE MER
	{id = "{HB_A6E_MK20_MER_5x_RIGHT}",				pylons = {0,1,0,1,0}}, -- ROCKEYE MER 011111
	{id = "{HB_A6E_MK20_MER_4x_RIGHT}",				pylons = {1,1,0,1,1}}, -- ROCKEYE MER 011010
	{id = "{HB_A6E_MK20_MER_3x_RIGHT}",				pylons = {1,1,0,1,1}}, -- ROCKEYE MER 011010
	{id = "{HB_A6E_MK20_MER_2x}",					pylons = {1,1,0,1,1}}, -- ROCKEYE MER 010010
	{id = "{HB_A6E_MK20_MER_1x}",					pylons = {1,1,0,1,1}}, -- ROCKEYE MER 010000

	{id = "", pylons = {1,1,1,1,1}}, -- CBU-78 AERO
	{id = "", pylons = {1,0,1,0,1}}, -- CBU-78 TER
	{id = "", pylons = {0,1,0,1,0}}, -- CBU-78 TER 011
	{id = "", pylons = {1,0,1,0,1}}, -- CBU-78 MER
	{id = "", pylons = {0,1,0,1,0}}, -- CBU-78 MER 011111

	{id = "", pylons = {1,1,1,1,1}}, -- CBU-59 AERO
	{id = "", pylons = {0,0,1,0,0}}, -- CBU-59 TER
	{id = "", pylons = {1,1,0,1,1}}, -- CBU-59 TER 011
	{id = "", pylons = {1,1,0,1,1}}, -- CBU-59 MER 011011
	{id = "", pylons = {0,0,1,0,0}}, -- CBU-59 MER 101101

	-- Mines
	{id = "", pylons = {1,1,1,1,1}}, -- MK52 AERO
	{id = "", pylons = {1,1,1,1,1}}, -- MK55 AERO
	{id = "", pylons = {1,1,1,1,1}}, -- MK56 AERO
	{id = "", pylons = {1,1,1,1,1}}, -- MK60 CAPTOR AERO
	{id = "", pylons = {1,1,1,1,1}}, -- MK65 QUICKSTIRKE AERO

	-- AA Missiles
	{id = "",					pylons = {1,1,0,1,1}}, -- AIM-9H LAU7

	-- AG Missiles
	{id = "{LAU_34_AGM_45A}",						pylons = {1,1,0,1,1}}, -- SHRIKE AERO/LAU118

	-- Fuel Bags
	{id = "{HB_A6E_AERO1D}",		pylons = {1,1,1,1,1},	attach_point_position = { 0.0, -0.32, 0.0}}, -- AERO-1D 300GAL
	{id = "{HB_A6E_AERO1D_EMPTY}",	pylons = {1,1,1,1,1},	attach_point_position = { 0.0, -0.32, 0.0}}, -- AERO-1D 300GAL EMPTY
}

A6A_weapons =
{
	-- AG Missiles
	{id = "{AGM_12B}",								pylons = {1,1,0,1,1}}, -- AGM-12 BULLPUP AERO

	-- AA Missiles
	{id = "{HB_A6E_LAU7_AIM9B}",					pylons = {1,1,0,1,1}}, -- AIM-9B LAU7
	{id = "",										pylons = {1,1,0,1,1}}, -- AIM-9G LAU7
}

A6B_weapons =
{
	-- AG Missiles
	{id = "{HB_A6E_AGM_78}", pylons = {1,1,0,1,1}}, -- STARM LAU77
}

A6E_BASE_weapons =
{
	-- Other
	{id = "{HB_A6E_D704}", pylons = {0,0,1,0,0}, arg_value = 1}, -- 31-300 OR D-704 OR A/A43R-1 REFUELING STORE

	-- AA Missiles
	{id = "{HB_A6E_LAU7_AIM9L}",	pylons = {1,1,0,1,1}}, -- AIM-9L LAU7
	{id = "{HB_A6E_LAU7_AIM9M}",	pylons = {1,1,0,1,1}}, -- AIM-9M LAU7
	{id = "",						pylons = {1,1,0,1,1}}, -- ATM-9 LAU7
	--{id = "{LAU-7 - TCTS}",			pylons = {1,1,0,1,1}}, -- TACTS LAU7
}

A6E_AWG21_weapons =
{
	-- AG Missiles
	{id = "{HB_A6E_AGM_78}", pylons = {1,1,0,1,1}}, -- STARM LAU77
}

A6E_TRAM_weapons =
{
	-- AG Missiles
	{id = "",										pylons = {1,1,0,1,1}}, -- SKIPPER AERO

	-- Fuel Bags
	{id = "",						pylons = {1,1,1,1,1}}, -- ATP-D1B 400GAL
	{id = "",						pylons = {1,1,1,1,1}}, -- ATP-D1B 400GAL EMPTY

	-- Other
	{id = "", pylons = {1,1,0,1,1}}, -- CTU-2/A CONTAINER
	{id = "", pylons = {1,1,1,1,1}}, -- CNU-188/A CONTAINER
	{id = "{CAE48299-A294-4bad-8EE6-89EFC5DCDF00}",	pylons = {1,1,0,1,1}, connector_name = "", attach_point_oriented = false, attach_point_position = {0,0.0,0.005}}, -- SUU-25 AERO
	{id = "{HB_A6E_SUU25_TER_3x}", pylons = {1,0,0,0,1}}, -- SUU-25 TER
	{id = "{HB_A6E_SUU25_MER_2x_RIGHT}", pylons = {1,0,0,0,1}}, -- SUU-25 MER 000011

	-- Not listing target drones

	-- Countermeasures
	{id = "",	pylons = {1,0,0,1,1}}, -- ALE-37A
	{id = "",	pylons = {1,0,0,1,1}}, -- ALE-41
	{id = "{F14-ALQ167-POD}",	pylons = {1,0,0,1,1}}, -- ALQ-167
}

A6E_SWIP_weapons =
{
	-- AG Missiles
	{id = "{B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", pylons = {1,1,0,1,1}}, -- HARM LAU118
	{id = "{AGM_84D}",								pylons = {1,1,0,1,1},	attach_point_position = { 0.0, -0.17, 0.0}}, -- HARPOON AERO
	{id = "{F16A4DE0-116C-4A71-97F0-2CF85B0313EC}",	pylons = {1,1,0,1,1}}, -- AGM-65E
	{id = "LAU_117_AGM_65F",						pylons = {1,1,0,1,1}}, -- AGM-65F
	{id = "{AGM_84E}",								pylons = {0,1,0,1,0}}, -- SLAM
	{id = "{AGM_62_I}",								pylons = {0,1,0,1,0}}, -- WALLEYE

	-- Countermeasures
	{id = "{HB_A6E_TALD_MER_4x}",		Type = 1,	pylons = {1,0,0,0,1}}, -- TALD MER 101101
	{id = "{HB_A6E_TALD_MER_2x}",		Type = 1,	pylons = {1,1,0,1,1}}, -- TALD MER 010010
	{id = "{HB_A6E_TALD_MER_2x_RIGHT}",	Type = 1,	pylons = {1,0,0,0,1}}, -- TALD MER 001001
}

function GetPylonWeaponsTableByAircraftType(aircraft, pylon)
	if aircraft == 'A6A' then
		tbl = joinTables(GetPylonWeaponsTable(A6_SHARED_weapons, pylon),GetPylonWeaponsTable(A6A_weapons, pylon))
		return tbl
	elseif aircraft == 'A6B' then
		tbl = joinTables(GetPylonWeaponsTable(A6_SHARED_weapons, pylon),GetPylonWeaponsTable(A6A_weapons, pylon))
		tbl2 = joinTables(tbl,GetPylonWeaponsTable(A6B_weapons, pylon))
		return tbl2
	elseif aircraft == 'KA6D' then
		tbl = GetPylonWeaponsTable(A6_SHARED_weapons, pylon)
		return tbl
	elseif aircraft == 'A6E' then
		tbl = joinTables(GetPylonWeaponsTable(A6_SHARED_weapons, pylon),GetPylonWeaponsTable(A6E_BASE_weapons, pylon))
		tbl2 = joinTables(tbl,GetPylonWeaponsTable(A6E_TRAM_weapons, pylon))
		tbl3 = joinTables(tbl2,GetPylonWeaponsTable(A6E_SWIP_weapons, pylon))
		return tbl3
	else
		return {}
	end

	-- Editor requires re-indexing of table to ensure there are no gaps (otherwise you can't edit loadouts properly)
	local indexed_weapon_table = {}
	for _, v in pairs(weapon_table) do
		table.insert(indexed_weapon_table, v)
	end

	return indexed_weapon_table
end

function GetPylonWeaponsTable(source_table, pylon)
	tbl = {}
	for k,v in ipairs(source_table) do
		if (v.pylons[pylon] == 1) then
			local id = v.id
			-- Check to swap l/r-hand loadouts
			if (string.find(id, "_RIGHT") and (pylon == 1 or pylon == 2)) then
				id = string.gsub(id, "_RIGHT", "_LEFT")
			end

			tbl[#tbl+1] =
			{
				CLSID = id,
				arg_value = v.arg_value or 0,
				attach_point_position = v.attach_point_position or {0,0,0},
				connector_name = v.connector_name or "PYLON"..pylon,
				attach_point_oriented = v.attach_point_oriented or true,
			}
		end
	end
	return tbl
end

function joinTables(result, tbl2)
	for _, t in ipairs(tbl2) do
		table.insert(result, t)
	end
	return result
end