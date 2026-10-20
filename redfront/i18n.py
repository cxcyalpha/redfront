"""Язык интерфейса и брифинга: русский (по умолчанию) или английский.

Язык кампании - st["settings"]["lang"] ("ru" / "en"); окно браузера хранит выбор у себя и передаёт его в кампанию.
Переводятся: названия задач, групп и ролей доктрин (каталог TITLES), статусы, сообщения окна и брифинг миссии.
Имена частей, пунктов и аэродромов - как в составе сил. Журнал событий модели и пояснения целей пока по-русски.
"""
from __future__ import annotations

TITLES = {
    # задачи доктрин
    "Вертолётный десант": "Helicopter air assault",
    "Воздушная перевозка": "Airlift",
    "Воздушная разведка": "Air reconnaissance",
    "Дежурство ДРЛО": "AWACS station",
    "Дежурство ПВО на аэродроме": "QRA alert",
    "Дежурство заправщика": "Tanker station",
    "Изоляция поля боя (BAI): колонна у переднего края": "Battlefield air interdiction (BAI): column near the FLOT",
    "Поиск и спасение": "Combat search and rescue",
    "Прикрытие войск": "Defensive counter-air over own troops",
    "Удар вертолётов по войскам в соприкосновении": "Attack helicopter strike on troops in contact",
    "Удар по аэродрому": "Airfield strike",
    "Удар по войскам в соприкосновении": "Close air support",
    "Удар по вторым эшелонам (FOFA)": "Follow-on forces attack (FOFA)",
    "Удар по заводу": "Factory strike",
    "Удар по колонне на марше": "Strike on a column on the march",
    "Удар по мосту": "Bridge strike",
    "Удар по позиции ЗРК": "SAM site strike",
    "Удар по путям подвоза": "Supply route interdiction",
    "Удар по складу": "Depot strike",
    "Эвакуация десанта": "Air assault extraction",
    # группы пакета
    "ударная группа": "strike group",
    "ударная группа вертолётов": "attack helicopter group",
    "группа добивания ЗРК": "SAM kill group",
    "группа добивания ЗРК (killer)": "SAM kill group (killer)",
    "группа доразведки, поиска и поражения": "armed reconnaissance group",
    "группа подавления ПВО": "SEAD group",
    "группа подавления ПВО (hunter)": "SEAD group (hunter)",
    "группа прикрытия": "escort group",
    "группа прикрытия (Ми-24)": "escort group (Mi-24)",
    "группа прикрытия (ударные вертолёты)": "escort group (attack helicopters)",
    "группа расчистки воздуха": "fighter sweep",
    "демонстративная группа": "feint group",
    "десантная группа": "assault lift group",
    "эвакуационная группа": "extraction group",
    "поисково-спасательная группа": "rescue group",
    "транспортная группа": "transport group",
    "разведчик": "reconnaissance aircraft",
    "разведчик-наводчик (SA342)": "scout (SA342)",
    "дежурная пара": "alert pair",
    "дежурное звено": "alert flight",
    "дежурство дрло": "AWACS station",
    "дежурство заправщика": "tanker station",
    "пара": "pair",
    "пара CAP": "CAP pair",
    "пара прикрытия": "escort pair",
    # роли
    "боевые вертолёты": "attack helicopters",
    "бомбардировочная авиация": "bomber aviation",
    "военно-транспортная авиация": "military transport aviation",
    "истребители-перехватчики": "interceptors",
    "истребительная авиация": "fighter aviation",
    "истребительно-бомбардировочная авиация": "fighter-bomber aviation",
    "разведывательная авиация": "reconnaissance aviation",
    "самолёты ДРЛО и управления": "AWACS aircraft",
    "самолёты-заправщики": "tanker aircraft",
    "транспортные вертолёты": "transport helicopters",
    "штурмовая авиация": "ground attack aviation",
    # статусы плана полётов
    "слетан игроком": "flown by player",
    "прошёл": "completed",
    "в воздухе": "airborne",
    "по плану": "planned",
}


WAYPOINTS = {"Взлёт": "Takeoff", "Посадка": "Landing", "Демонстрация": "Feint", "Зона дежурства": "Station", "Зона прикрытия": "Escort zone", "Зона расчистки": "Sweep zone",
             "ИПМ": "IP", "Маршрут": "Route", "Отход": "Egress", "Площадка": "LZ", "Площадка (прикрытие)": "LZ (escort)",
             "Подход": "Approach", "Район поиска": "Search area", "Рубеж атаки": "Attack line", "Рубеж пуска": "Launch line",
             "Сбор": "Rendezvous", "Снижение": "Descent", "Уход": "Egress", "Цель": "Target", "Экипаж": "Crew",
             "Разведка": "Recce"}


def waypoint(name: str, lg: str) -> str:
    if lg != "en" or not name:
        return name
    if name in WAYPOINTS:
        return WAYPOINTS[name]
    head, _sp, num = name.rpartition(" ")
    return f"{WAYPOINTS[head]} {num}" if head in WAYPOINTS else name


def lang(state: dict | None) -> str:
    return ((state or {}).get("settings") or {}).get("lang") or "ru"


def tr(text: str, lg: str) -> str:
    """Название по каталогу; "Название: подробности" - переводится название (до первого ': ')."""
    if lg != "en" or not text:
        return text
    if text in TITLES:
        return TITLES[text]
    head, sep, rest = text.partition(": ")
    if sep and head in TITLES:
        return TITLES[head] + sep + rest
    for suffix in (" (2)", " (3)"):
        if text.endswith(suffix) and text[:-len(suffix)] in TITLES:
            return TITLES[text[:-len(suffix)]] + suffix
    return text


def L(lg: str, ru: str, en: str) -> str:
    """Строка на языке lg."""
    return en if lg == "en" else ru
