"""Пакет доктрины 'nato' (data/doctrine/nato.json): задачи общего профиля и ВД, переложенные на тактическую доктрину
НАТО 1970-1990 по источникам. Запуск: python tools/gen_nato.py (перезаписывает nato.json)."""
import copy
import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "redfront" / "data" / "doctrine"
RAND = "RAND R-3385-AF (D. Stein, The Development of NATO Tactical Air Doctrine 1970-1985, 1987)"
ATP27 = "ATP-27(C)/AJP-3.3.2 Air Interdiction and Close Air Support (1999)"
FM101 = "FM 101-20 United States Army Aviation Planning Manual (1984), табл. 1-5"
AJP33 = "AJP-3.3(B) Allied Joint Doctrine for Air and Space Operations (2016)"

gen = json.loads((D / "generic.json").read_text(encoding="utf-8"))
wp = json.loads((D / "wp.json").read_text(encoding="utf-8"))
t = copy.deepcopy(gen["tasks"])
sead = copy.deepcopy(next(s for s in wp["tasks"]["strike_airfield"]["support"] if s["id"] == "sead"))
cover = copy.deepcopy(next(s for s in wp["tasks"]["strike_column_march"]["support"] if s["id"] == "cover"))
recon_sup = copy.deepcopy(next(s for s in wp["tasks"]["strike_column_march"]["support"] if s["id"] == "recon"))

# подавление ПВО: у союзников - обеспечивающее действие без своих средств; выделенные средства SEAD - только у США
sead.update({"required": False, "nations": ["us"], "min_fit": 0.5, "performers": ["fighter_bomber", "fighter", "attack"],
             "source": f"{RAND}, с. 46-49: в НАТО SEAD - обеспечивающее действие (ATP-33(A), ATP-27(B)); выделенные "
                       "средства подавления ПВО в начале 80-х - только у ВВС США, их вероятное применение - 'открывать "
                       "коридоры' для авиации НАТО; союзники (Великобритания, Бельгия, Нидерланды) - 'быстрее и ниже'",
             "required_note": "у НАТО пакет без группы подавления ПВО допустим (союзники прорываются на малой высоте); "
                              "группа ставится, если есть часть США, которая может её дать"})
cover.update({"source": f"{RAND}, с. vii: ВВС США первым приоритетом ставят завоевание господства в воздухе - "
                        "истребители прикрытия ударных групп"})
for k in ("strike_airfield", "strike_bridge", "strike_depot", "strike_factory", "strike_sam_site"):
    t[k]["support"] = [copy.deepcopy(sead), copy.deepcopy(cover)]
    t[k]["method_source"] = f"{ATP27}, 301-302: воздушная изоляция (AI) - удары за FSCL по военному потенциалу и по " \
                            "тому, что его ограничивает (управление, пути, тыл)"
t["strike_supply_route"]["support"] = [copy.deepcopy(sead)]

# BAI - удар по колоннам у переднего края (с ATP-27(B), 1980); FOFA - по вторым эшелонам в глубине (с 1983)
col = copy.deepcopy(wp["tasks"]["strike_column_march"])
col["performers"] = ["attack", "fighter_bomber", "bomber"]
col["support"] = [copy.deepcopy(sead), copy.deepcopy(cover)]   # группа доразведки - понятие ВД (3.3.3), у НАТО - нет
bai = copy.deepcopy(col)
bai.update({"title": "Изоляция поля боя (BAI): колонна у переднего края", "from_year": 1980,
            "method_source": f"{RAND}, с. 28-33: BAI введена в ATP-27(B) (1980) по предложению Великобритании - удары "
                             "по бронетанковым частям ОВД, ещё не вступившим в бой, в 15-50 км за передним краем "
                             "(приоритет NORTHAG; своё оружие корпусов - 20-25 км); планирование совместно с сухопутными "
                             "войсками, исполнение - под руководством ВВС"})
bai["target"] = {"category": "ground", "state": "march", "depth_km": [15, 50]}
fofa = copy.deepcopy(col)
fofa.update({"title": "Удар по вторым эшелонам (FOFA)", "from_year": 1983,
             "method_source": f"{RAND}, с. 36-44: концепция FOFA (директива SACEUR 80-31 для ACE, 1983) - задержать, "
                              "разрушить, расстроить вторые эшелоны ОВД до вступления в бой; по ATP-33 это воздушная "
                              "изоляция; полосы: от FSCL - решение корпуса и группы армий, до ~400 км - крупного "
                              "командования. Глубина 50-150 км - ОЦЕНКА по радиусу тактической авиации сектора"})
fofa["target"] = {"category": "ground", "state": "march", "depth_km": [50, 150]}
t["cas_contact"]["method_source"] = f"{ATP27}, 401: непосредственная авиационная поддержка (CAS) - по целям в " \
    f"непосредственной близости от своих войск, с детальной увязкой; {RAND}, с. 43: от своих войск до FSCL ~20-30 км"
t["cas_helo"]["method_source"] = f"{ATP27}, 401.4: совместные действия вертолётов и самолётов (JAAT)"
t["cap_own_troops"]["method_source"] = f"{RAND}, с. vii, 41: прикрытие войск - оборонительная борьба за господство " \
    "в воздухе (DCA); у ФРГ - второй приоритет после боя с первым эшелоном"

t["strike_bai"], t["strike_fofa"] = bai, fofa
FM100 = "FM 100-103 Army Airspace Command and Control in a Combat Zone (1987), 2-12...2-13, рис. 2-5"
for k, v in t.items():                       # маршруты малой высоты (LLTR/MRR): к цели 100 футов, обратно - выше 500
    if v.get("method") in ("on_call", "interdiction", "sequential_on_call") and "attack_helo" not in v["performers"]:
        v["transit_alt_m_agl"] = 30
        v["egress_alt_m_agl"] = 150
        v["transit_alt_source"] = f"{FM100}: маршрут пролёта на малой высоте (LLTR, у ВВС США - MRR) от тыла корпуса до FSCL - " \
                                  "к цели на 100 футов, возвращающиеся - выше 500 футов; ПВО в коридоре - 'огонь запрещён'. " \
                                  "ИИ DCS - не ниже 100 м (build.AI_LOW_MIN_M)"

order = ["csar", "air_evac", "cas_contact", "cas_helo", "strike_bai", "cap_own_troops", "strike_airfield",
         "strike_sam_site", "strike_fofa", "strike_supply_route", "strike_bridge", "strike_depot", "strike_factory",
         "air_assault", "awacs_orbit", "tanker_orbit", "airlift", "recon", "qra"]
tasks = {k: t[k] for k in order}

doc = {
    "_about": "Пакет доктрины 'НАТО (Центральный фронт, 1970-1990)'. Работает с ролями (roles.json). Источники - поле "
              f"source/method_source: {RAND}; {ATP27}; {AJP33}. Числа высот, скоростей, размеров групп - ОЦЕНКИ "
              "общего профиля (estimate_fields), как у пакета generic. Сгенерирован tools/gen_nato.py.",
    "package": "nato",
    "title": "НАТО (Центральный фронт)",
    "tasks": tasks,
    "march": gen["march"],
    "sim": gen["sim"],
    "task_priority_note": f"Порядок задач = приоритет плана дня: войска в соприкосновении и первый эшелон (CAS, BAI), "
                          f"затем борьба за господство в воздухе (DCA, OCA), подавление ПВО, затем вторые эшелоны и тыл "
                          f"(FOFA, AI). {RAND}, с. 41, 43: приоритеты ФРГ (ген. Альтенбург) - бой с первым эшелоном, "
                          "ПВО, затем вторые эшелоны; англичане - CAS и BAI ближе к фронту.",
    "apportionment": {
        "source": f"{AJP33}, 4.5 и пример с. 4-18 (DCA 40, OCA 25, APCLO 25, SEAD 10%) - формат; доли здесь - ОЦЕНКА "
                  f"для обороны Центрального фронта 80-х ({RAND}: приоритет боя с первым эшелоном у союзников): "
                  "больше на поддержку войск, меньше на DCA",
        "classes": {"DCA": ["cap_own_troops"], "OCA": ["strike_airfield"], "SEAD": ["strike_sam_site"],
                    "APCLO": ["cas_contact", "cas_helo", "strike_bai", "strike_fofa", "strike_supply_route",
                              "strike_bridge", "strike_depot", "strike_factory"]},
        "shares": [{"from_day": 1, "DCA": 0.25, "OCA": 0.15, "SEAD": 0.1, "APCLO": 0.5},
                   {"from_day": 4, "DCA": 0.2, "OCA": 0.1, "SEAD": 0.1, "APCLO": 0.6}],
        "estimate": True,
    },
    "nation_bonus": {
        "source": f"{RAND}, с. v-vii, 26-28, 43: 2-е ОТАК (Великобритания, ФРГ, Бельгия, Нидерланды, NORTHAG) - тесная "
                  "увязка с сухопутными войсками, CAS и BAI у переднего края; 4-е ОТАК (ВВС США, CENTAG) - "
                  "централизованное управление, господство в воздухе первым, удары в глубину. Величины - ОЦЕНКА.",
        "uk": {"cas": 0.15, "interdiction": 0.1}, "frg": {"cas": 0.15}, "be": {"cas": 0.1}, "nl": {"cas": 0.1},
        "us": {"air": 0.1, "strike": 0.1, "sead": 0.15},
    },
}
(D / "nato.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("nato.json:", list(tasks))
