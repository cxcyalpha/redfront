# Сторонние скрипты в этой папке

Файлы лежат без изменений. Сборка миссии (`redfront/build.py`) меняет только копию `CTLD.lua`, которая
кладётся в `.miz`: в ней ставится `ctld.dontInitialize = true`, чтобы redfront сначала задал свою настройку
(`redfront/lua/ctld_cfg.lua`), а потом сам вызвал `ctld.initialize()`.

## CTLD.lua — DCS-CTLD 1.6.1

- Источник: https://github.com/ciribob/DCS-CTLD, коммит 82e87bf866409068f023253e55625347b34a4e0d (2025-12-12).
- Авторы: Ciribob; сейчас поддерживают Zip и команда VEAF (https://www.veaf.org).
- Лицензия (README проекта): «open-source and free as in free beer (you don't have to pay to use it), and as in free of use
  (you can use it, modify it and publish a fork if you want, even make a commercial profit). Credit is appreciated where
  it's due.»

## mist.lua — MIST 4.5.128-DYNSLOTS-02

- Это копия из поставки DCS-CTLD: CTLD требует именно эту версию.
- Источник: https://github.com/mrSkortch/MissionScriptingTools.
- Авторы: Speed, Grimes, lukrop.
- Распространяется вместе с CTLD и встраивается в миссии DCS, как в сообществе принято.

Перевод сообщений CTLD на русский — `redfront/lua/ctld_ru.lua`. Это собственный файл redfront, а не часть CTLD.
