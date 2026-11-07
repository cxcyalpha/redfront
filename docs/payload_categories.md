# Ключи своих подвесок

Имя подвески в редакторе миссий DCS = ключ. Подвеска - самая современная: по году кампании оружие заменит weapons.degrade. Импорт: `python tools/import_payloads.py --custom <Saved Games\DCS\MissionEditor\UnitPayloads>`.

Порядок поиска: `задача/группа` -> `группа` или `задача` -> категория -> подвеска Retribution.

## Категории (общие)

| Ключ | Что |
|---|---|
| `cap` | прикрытие, дежурство ПВО, барражирование (воздух-воздух, топливо) |
| `escort` | сопровождение ударной группы (воздух-воздух) |
| `strike` | удар по объекту (мосты, склады, заводы) |
| `bombs` | бомбы общего назначения |
| `bai` | удар по колоннам и путям подвоза, изоляция |
| `cas` | непосредственная поддержка войск |
| `anti_armor` | противотанковое |
| `sead` | подавление ПВО (ПРР) |
| `dead` | уничтожение ЗРК |
| `runway` | удар по аэродрому (ВПП) |
| `antiship` | удар по кораблям |

## Задачи (ударная группа)

| Ключ | Задача |
|---|---|
| `cap_object` | Барражирование над прикрываемым районом |
| `cap_own_troops` | Прикрытие войск |
| `cas_contact` | Удар по войскам в соприкосновении |
| `cas_helo` | Удар вертолётов по войскам в соприкосновении |
| `fleet_cap` | Прикрытие соединения |
| `qra` | Дежурство ПВО на аэродроме |
| `strike_airfield` | Удар по аэродрому |
| `strike_b52` | Удар B-52 (ячейки по три) |
| `strike_bai` | Изоляция поля боя (BAI): колонна у переднего края |
| `strike_bridge` | Удар по мосту |
| `strike_column_march` | Удар по колонне на марше |
| `strike_depot` | Удар по складу |
| `strike_factory` | Удар по заводу |
| `strike_fofa` | Удар по вторым эшелонам (FOFA) |
| `strike_sam_site` | Удар по позиции ЗРК |
| `strike_ship` | Удар по кораблям |
| `strike_supply_route` | Удар по путям подвоза |

## Группы обеспечения

Ключ группы для всех задач: `cover`, `feint`, `flak`, `kill`, `migcap`, `recon`, `scout`, `sead`, `sweep`.

| Ключ | Группа |
|---|---|
| `cas_contact/cover` | Удар по войскам в соприкосновении: группа прикрытия |
| `cas_contact/kill` | Удар по войскам в соприкосновении: группа добивания ЗРК |
| `cas_contact/sead` | Удар по войскам в соприкосновении: группа подавления ПВО |
| `cas_helo/scout` | Удар вертолётов по войскам в соприкосновении: разведчик-наводчик (SA342) |
| `strike_airfield/cover` | Удар по аэродрому: группа прикрытия |
| `strike_airfield/feint` | Удар по аэродрому: демонстративная группа |
| `strike_airfield/flak` | Удар по аэродрому (налёт 'Альфа'): подавление зенитной артиллерии над целью |
| `strike_airfield/kill` | Удар по аэродрому: группа добивания ЗРК |
| `strike_airfield/migcap` | Удар по аэродрому (налёт 'Альфа'): MiGCAP (расчистка воздуха) |
| `strike_airfield/sead` | Удар по аэродрому: группа подавления ПВО |
| `strike_airfield/sweep` | Удар по аэродрому: группа расчистки воздуха |
| `strike_b52/migcap` | Удар B-52 (ячейки по три): MiGCAP (расчистка воздуха) |
| `strike_b52/sead` | Удар B-52 (ячейки по три): 'Айрон Хэнд' / 'Дикая ласка' (подавление С-75) |
| `strike_bai/cover` | Изоляция поля боя (BAI): колонна у переднего края: группа прикрытия |
| `strike_bai/kill` | Изоляция поля боя (BAI): колонна у переднего края: группа добивания ЗРК (killer) |
| `strike_bai/sead` | Изоляция поля боя (BAI): колонна у переднего края: группа подавления ПВО (hunter) |
| `strike_bridge/cover` | Удар по мосту: группа прикрытия |
| `strike_bridge/flak` | Удар по мосту (налёт 'Альфа'): подавление зенитной артиллерии над целью |
| `strike_bridge/kill` | Удар по мосту: группа добивания ЗРК |
| `strike_bridge/migcap` | Удар по мосту (налёт 'Альфа'): MiGCAP (расчистка воздуха) |
| `strike_bridge/sead` | Удар по мосту: группа подавления ПВО |
| `strike_bridge/sweep` | Удар по мосту: группа расчистки воздуха |
| `strike_column_march/cover` | Удар по колонне на марше: группа прикрытия |
| `strike_column_march/kill` | Удар по колонне на марше: группа добивания ЗРК |
| `strike_column_march/recon` | Удар по колонне на марше: группа доразведки, поиска и поражения |
| `strike_column_march/sead` | Удар по колонне на марше: группа подавления ПВО |
| `strike_depot/cover` | Удар по складу: группа прикрытия |
| `strike_depot/feint` | Удар по складу: демонстративная группа |
| `strike_depot/flak` | Удар по складу (налёт 'Альфа'): подавление зенитной артиллерии над целью |
| `strike_depot/kill` | Удар по складу: группа добивания ЗРК |
| `strike_depot/migcap` | Удар по складу (налёт 'Альфа'): MiGCAP (расчистка воздуха) |
| `strike_depot/sead` | Удар по складу: группа подавления ПВО |
| `strike_depot/sweep` | Удар по складу: группа расчистки воздуха |
| `strike_factory/cover` | Удар по заводу: группа прикрытия |
| `strike_factory/feint` | Удар по заводу: демонстративная группа |
| `strike_factory/flak` | Удар по заводу (налёт 'Альфа'): подавление зенитной артиллерии над целью |
| `strike_factory/kill` | Удар по заводу: группа добивания ЗРК |
| `strike_factory/migcap` | Удар по заводу (налёт 'Альфа'): MiGCAP (расчистка воздуха) |
| `strike_factory/sead` | Удар по заводу: группа подавления ПВО |
| `strike_factory/sweep` | Удар по заводу: группа расчистки воздуха |
| `strike_fofa/cover` | Удар по вторым эшелонам (FOFA): группа прикрытия |
| `strike_fofa/kill` | Удар по вторым эшелонам (FOFA): группа добивания ЗРК (killer) |
| `strike_fofa/sead` | Удар по вторым эшелонам (FOFA): группа подавления ПВО (hunter) |
| `strike_sam_site/cover` | Удар по позиции ЗРК: группа прикрытия |
| `strike_sam_site/kill` | Удар по позиции ЗРК: группа добивания ЗРК |
| `strike_sam_site/sead` | Удар по позиции ЗРК: группа подавления ПВО |
| `strike_ship/cover` | Удар по кораблям: группа прикрытия |
| `strike_ship/kill` | Удар по кораблям: группа добивания ЗРК |
| `strike_ship/sead` | Удар по кораблям: группа подавления ПВО |
| `strike_supply_route/cover` | Удар по путям подвоза: группа прикрытия |
| `strike_supply_route/kill` | Удар по путям подвоза: группа добивания ЗРК |
| `strike_supply_route/sead` | Удар по путям подвоза: группа подавления ПВО |

## Типы ЛА

| Тип DCS | Где |
|---|---|
| A-10A | germany, germany_1985, germany_1987 |
| A-4E-C | мод a4ec |
| A-50 | caucasus, germany, germany_1985, germany_1987 |
| A6E | lebanon83, vietnam72, vietnam72_lb2 |
| AH-1W | lebanon83, syria, vietnam72, vietnam72_lb2 |
| AH-64A | germany, germany_1987 |
| AH-64D_BLK_II | версия для игрока |
| AV8BNA | germany, germany_1985, germany_1987 |
| A_4E_C | golan73, syria |
| An-26B | germany, germany_1985, germany_1987 |
| B-52H | vietnam72, vietnam72_lb2 |
| C-130J-30 | germany, germany_1985, germany_1987 |
| CH-47Fbl1 | germany, germany_1985, germany_1987 |
| CH-53E | germany, germany_1985, germany_1987, golan73, vietnam72, vietnam72_lb2 |
| E-2C | lebanon83, syria, vietnam72, vietnam72_lb2 |
| E-3A | germany, germany_1985, germany_1987 |
| F-14A-135-GR | lebanon83 |
| F-14A-135-GR-Early | vietnam72, vietnam72_lb2 |
| F-15C | germany, germany_1985, germany_1987, syria |
| F-16A | syria |
| F-16C_50 | germany, germany_1985, germany_1987 |
| F-4E-45MC | germany, germany_1985, germany_1987, golan73, hamburg, syria, vietnam72, vietnam72_lb2 |
| FA-18C_hornet | germany, germany_1985, germany_1987, lebanon83, vietnam72, vietnam72_lb2 |
| KC-135 | germany, germany_1985, germany_1987, syria, vietnam72, vietnam72_lb2 |
| KC130J | мод uh60l |
| L-39C | caucasus |
| L-39ZA | germany, germany_1985, germany_1987 |
| Mi-24P | caucasus, germany, germany_1985, germany_1987 |
| Mi-26 | germany, germany_1985, germany_1987 |
| Mi-8MT | caucasus, germany, germany_1985, germany_1987, golan73, syria |
| MiG-15bis | golan73, vietnam72, vietnam72_lb2 |
| MiG-19P | vietnam72, vietnam72_lb2 |
| MiG-21Bis | germany, germany_1985, germany_1987, golan73, lebanon83, syria, vietnam72, vietnam72_lb2 |
| MiG-23MLD | germany, germany_1985, germany_1987, lebanon83, syria |
| MiG-25PD | germany_1985, germany_1987, syria |
| MiG-25RBT | germany, germany_1985, germany_1987 |
| MiG-27K | germany, germany_1985, germany_1987 |
| MiG-29 Fulcrum | germany, germany_1987, hamburg |
| MiG-29S | caucasus |
| Mirage-F1CE | golan73 |
| S-3B Tanker | lebanon83, vietnam72, vietnam72_lb2 |
| SA342M | germany, germany_1985, germany_1987, lebanon83, syria |
| Su-17M4 | germany, germany_1985, germany_1987, golan73, lebanon83, syria |
| Su-24M | caucasus, germany_1985, germany_1987, hamburg |
| Su-24MR | caucasus, germany, germany_1985, germany_1987 |
| Su-25 | caucasus, germany, germany_1987, hamburg |
| Su-27 | caucasus |
| Su-30MKA | мод su30 |
| Su-30MKI | мод su30 |
| Su-30MKM | мод su30 |
| Su-30SM | мод su30 |
| Su-35S | мод su35s |
| Tornado GR4 | germany, germany_1985, germany_1987 |
| Tornado IDS | germany, germany_1985, germany_1987, hamburg |
| Tu-22M3 | caucasus |
| UH-1H | caucasus, germany, germany_1985, germany_1987, golan73, syria, vietnam72, vietnam72_lb2 |
| UH-60A | germany, germany_1985, germany_1987 |
| UH-60L | версия для игрока, мод uh60l |
| UH-60L_DAP | мод uh60l |
| Yak-40 | germany, germany_1985, germany_1987 |
