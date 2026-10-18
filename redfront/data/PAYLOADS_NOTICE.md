# payloads.json - подвески по задачам из DCS Retribution

- Источник: https://github.com/dcs-retribution/dcs-retribution, `resources/customized_payloads/*.lua`.
- Лицензия: GNU LGPL-3.0 (как у проекта DCS Retribution). Данные переведены из Lua в JSON без изменений по составу
  пилонов (`tools/import_payloads.py`); имена подвесок - как в источнике ("Retribution CAS", "STRIKE" ...).
- Авторы - участники проекта DCS Retribution (и DCS Liberation, из которого он вырос).
- redfront выбирает подвеску по виду задачи (`build.loadout_cats`, `PAYLOAD_NAMES`) и затем меняет оружие по году
  кампании (`redfront/weapons.py`) - эти правила не из Retribution.
