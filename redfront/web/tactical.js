// redfront: тактическая карта окна кампании - условные знаки и линия фронта.
// Стиль - по стороне игрока: за красных - советская рабочая карта (свои красным, противник синим, оборона - дуга к
// противнику, марш - стрелка, район сосредоточения - овал, подписи "94 гв. мсд"), за синих - APP-6 НАТО (свои -
// синие прямоугольники, противник - красные ромбы, знак рода войск в рамке, звено над рамкой).
// Линия фронта: граница территорий сторон - "кто ближе" по пунктам и частям в поле (диаграмма Вороного на сетке),
// изолинии по обе стороны границы: красная - передний край красных, синяя - синих.
"use strict";
const TAC = (() => {
  const RED = "#c8102e", BLUE = "#1f4fbf", GREY = "#6b6b6b", INK = "#222";
  const sideCol = s => s === "red" ? RED : s === "blue" ? BLUE : GREY;
  const KM_LAT = 111.32;
  const merc = lat => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
  const unmerc = y => (2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180 / Math.PI;

  // ---------- территория и линия фронта ----------
  // sites: [{lat, lon, side}]; сетка равномерна в проекции Меркатора (картинка ложится на карту без искажения)
  function front(sites, opt) {
    opt = Object.assign({cols: 260, pad: 0.7, maxKm: 45, gapKm: 0.6}, opt || {});
    const red = sites.filter(s => s.side === "red"), blue = sites.filter(s => s.side === "blue");
    if (!red.length || !blue.length) return null;
    let la0 = 90, la1 = -90, lo0 = 180, lo1 = -180;
    for (const s of sites) { la0 = Math.min(la0, s.lat); la1 = Math.max(la1, s.lat); lo0 = Math.min(lo0, s.lon); lo1 = Math.max(lo1, s.lon); }
    la0 -= opt.pad; la1 += opt.pad; lo0 -= opt.pad; lo1 += opt.pad;
    const k = Math.cos((la0 + la1) / 2 * Math.PI / 180);
    const cols = opt.cols, y0 = merc(la0), y1 = merc(la1);
    const rows = Math.max(20, Math.round(cols * (y1 - y0) / ((lo1 - lo0) * Math.PI / 180)));
    const f = new Float32Array(cols * rows), near = new Float32Array(cols * rows);
    const lat = new Float32Array(rows), lon = new Float32Array(cols);
    for (let j = 0; j < rows; j++) lat[j] = unmerc(y1 - (y1 - y0) * (j + 0.5) / rows);   // строка 0 - север
    for (let i = 0; i < cols; i++) lon[i] = lo0 + (lo1 - lo0) * (i + 0.5) / cols;
    const R = red.map(s => [s.lat, s.lon]), B = blue.map(s => [s.lat, s.lon]);
    const nearest = (set, a, o) => { let m = 1e18; for (const p of set) { const dy = (p[0] - a) * KM_LAT, dx = (p[1] - o) * KM_LAT * k; const d = dx * dx + dy * dy; if (d < m) m = d; } return Math.sqrt(m); };
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
      const dr = nearest(R, lat[j], lon[i]), db = nearest(B, lat[j], lon[i]);
      f[j * cols + i] = dr - db;                     // < 0 - ближе красные
      near[j * cols + i] = Math.min(dr, db);
    }
    // заливка территорий (полупрозрачная, только вблизи пунктов и частей)
    const cv = document.createElement("canvas"); cv.width = cols; cv.height = rows;
    const cx = cv.getContext("2d"), img = cx.createImageData(cols, rows);
    for (let n = 0; n < cols * rows; n++) {
      if (near[n] > opt.maxKm) continue;
      const fade = Math.max(0, 1 - near[n] / opt.maxKm);
      const r = f[n] < 0;
      img.data[n * 4] = r ? 200 : 31; img.data[n * 4 + 1] = r ? 16 : 79; img.data[n * 4 + 2] = r ? 46 : 191;
      img.data[n * 4 + 3] = Math.round(28 * Math.min(1, 2.5 * fade));      // к краю - плавно на нет
    }
    cx.putImageData(img, 0, 0);
    const iso = level => contour(f, near, cols, rows, level, opt.maxKm).map(line => chaikin(chaikin(line)).map(([x, y]) =>
      [unmerc(y1 - (y1 - y0) * (y + 0.5) / rows), lo0 + (lo1 - lo0) * (x + 0.5) / cols]));
    return {image: cv.toDataURL(), bounds: [[la0, lo0], [la1, lo1]], red: iso(-opt.gapKm), blue: iso(opt.gapKm)};
  }

  // marching squares: изолиния f = level в клетках сетки, отрезки - в ломаные
  function contour(f, near, cols, rows, level, maxKm) {
    const segs = [];
    const v = (i, j) => f[j * cols + i] - level;
    const edge = (i, j, a, b) => {                 // точка на ребре между вершинами a и b клетки (i, j)
      const P = [[i, j], [i + 1, j], [i + 1, j + 1], [i, j + 1]];
      const pa = P[a], pb = P[b], va = v(...pa), vb = v(...pb), t = va / (va - vb);
      return [pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t];
    };
    for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) {
      if (near[j * cols + i] > maxKm) continue;
      const c = (v(i, j) > 0 ? 1 : 0) | (v(i + 1, j) > 0 ? 2 : 0) | (v(i + 1, j + 1) > 0 ? 4 : 0) | (v(i, j + 1) > 0 ? 8 : 0);
      if (c === 0 || c === 15) continue;
      const E = {t: () => edge(i, j, 0, 1), r: () => edge(i, j, 1, 2), b: () => edge(i, j, 2, 3), l: () => edge(i, j, 3, 0)};
      const pairs = {1: ["l", "t"], 2: ["t", "r"], 3: ["l", "r"], 4: ["r", "b"], 6: ["t", "b"], 7: ["l", "b"], 8: ["b", "l"],
                     9: ["b", "t"], 11: ["b", "r"], 12: ["r", "l"], 13: ["r", "t"], 14: ["t", "l"], 5: ["l", "t", "r", "b"], 10: ["t", "r", "b", "l"]}[c];
      for (let q = 0; q < pairs.length; q += 2) segs.push([E[pairs[q]](), E[pairs[q + 1]]()]);
    }
    // склейка отрезков по концам
    const key = p => `${p[0].toFixed(3)},${p[1].toFixed(3)}`;
    const ends = new Map();
    segs.forEach((s, n) => { for (const p of s) { const kk = key(p); (ends.get(kk) || ends.set(kk, []).get(kk)).push(n); } });
    const used = new Uint8Array(segs.length), lines = [];
    for (let n = 0; n < segs.length; n++) {
      if (used[n]) continue;
      used[n] = 1;
      const line = [segs[n][0], segs[n][1]];
      for (const dir of [1, 0]) {
        for (;;) {
          const tip = dir ? line[line.length - 1] : line[0];
          const nx = (ends.get(key(tip)) || []).find(m => !used[m]);
          if (nx === undefined) break;
          used[nx] = 1;
          const s = segs[nx], p = key(s[0]) === key(tip) ? s[1] : s[0];
          if (dir) line.push(p); else line.unshift(p);
        }
      }
      if (line.length > 3) lines.push(line);
    }
    return lines;
  }
  function chaikin(pts) {
    if (pts.length < 3) return pts;
    const out = [pts[0]];
    for (let n = 0; n < pts.length - 1; n++) {
      const a = pts[n], b = pts[n + 1];
      out.push([a[0] * .75 + b[0] * .25, a[1] * .75 + b[1] * .25], [a[0] * .25 + b[0] * .75, a[1] * .25 + b[1] * .75]);
    }
    out.push(pts[pts.length - 1]);
    return out;
  }

  // направление на ближайшего противника (градусы от севера по часовой)
  function bearingTo(pos, sites) {
    let best = null, m = 1e18;
    const k = Math.cos(pos[0] * Math.PI / 180);
    for (const s of sites) {
      const dy = s.lat - pos[0], dx = (s.lon - pos[1]) * k, d = dx * dx + dy * dy;
      if (d < m) { m = d; best = [dx, dy]; }
    }
    return best ? Math.atan2(best[0], best[1]) * 180 / Math.PI : 0;
  }
  function bearing(a, b) {
    const k = Math.cos(a[0] * Math.PI / 180);
    return Math.atan2((b[1] - a[1]) * k, b[0] - a[0]) * 180 / Math.PI;
  }

  // ---------- советские знаки (рабочая карта командира: Помбрик, Шевченко 1967; БУ СВ ч. II 1983) ----------
  // Цвета: наши мотострелки, танкисты, десант, авиация - красным; наши ПВО, артиллерия, спецвойска и ВСЕ надписи
  // наших - чёрным; противник целиком (знаки и надписи) - синим; маршруты наших - коричневым. Знаки наших направлены
  // к противнику и наоборот (ПВО - к верхнему обрезу карты). Надписи - горизонтально, наклонным шрифтом.
  const BROWN = "#7a4a1e";
  const ink = g => g.side === "blue" ? BLUE : INK;            // надписи: наши - чёрным, противника - синим
  // знак техники (носом вверх - к противнику): танк - ромб, БМП - "пуля" с чертой у кормы, БТР - "пуля",
  // вертолёт (десант) - транспортный вертолёт, пешие - без знака
  function suVehicle(v, c, x, y, rot, sc) {
    sc = sc || 1;
    const tf = `transform="translate(${x},${y}) rotate(${rot || 0}) scale(${sc})"`, st = `fill="#fffdf6" stroke="${c}" stroke-width="1.6"`;
    if (v === "tank") return `<path ${tf} ${st} d="M0 -7 L4 0 L0 7 L-4 0 Z"/>`;
    if (v === "bmp") return `<g ${tf}><path ${st} d="M0 -7 L3.5 -3 L3.5 6 L-3.5 6 L-3.5 -3 Z"/><path d="M-3.5 3.5 H3.5" stroke="${c}" stroke-width="1.6"/></g>`;
    if (v === "btr") return `<path ${tf} ${st} d="M0 -7 L3.5 -3 L3.5 6 L-3.5 6 L-3.5 -3 Z"/>`;
    if (v === "heli") return `<g transform="translate(${x},${y}) scale(${sc})" fill="none" stroke="${c}" stroke-width="1.6"><path d="M-6 -7 L6 -1 M6 -7 L-6 -1 M0 -4 V5"/><rect x="-2.5" y="5" width="5" height="3"/></g>`;
    return "";
  }
  // поперечные черточки звена на стрелке колонны: батальон - три, рота - две, взвод - одна (полк, дивизия - номером)
  const ticks = e => ({II: 3, I: 2}[e] || 0);
  function suShape(g, c, brg, dir) {
    const dash = g.state === "pending" ? ' stroke-dasharray="4 3"' : "";
    const big = g.echelon === "XX" ? 1.15 : g.echelon === "X" ? 1 : .85;
    const rx = (22 * big).toFixed(1), ry = (13 * big).toFixed(1);
    if (g.state === "march" && dir != null && g.order !== "attack") {     // колонна на технике: стрелка, знак на древке
      const n = ticks(g.echelon);
      let t = "";
      for (let k = 0; k < n; k++) t += `<path d="M-4 ${10 + 3 * k} H4" stroke="${c}" stroke-width="1.6"/>`;
      return `<g transform="rotate(${dir.toFixed(0)})"><path d="M0 22 V-20" stroke="${c}" stroke-width="2.2"/><path d="M0 -26 L-4 -17 L4 -17 Z" fill="${c}"/>${t}${suVehicle(g.vehicle, c, 0, 0)}</g>`;
    }
    if (g.order === "attack" && ["march", "battle"].includes(g.state)) {   // направление наступления: прерывистая стрелка
      const d = g.state === "march" && dir != null ? dir : brg;
      return `<g transform="rotate(${d.toFixed(0)})"><path d="M0 18 V-18" stroke="${c}" stroke-width="2.4" stroke-dasharray="7 4"/><path d="M0 -26 L-4.5 -16 L4.5 -16 Z" fill="${c}"/>` +
             `<path d="M-14 12 Q-14 4 -6 4 M14 12 Q14 4 6 4" fill="none" stroke="${c}" stroke-width="2"/>${suVehicle(g.vehicle, c, 0, 10, 0, .9)}</g>`;
    }
    if (g.state === "halted" || g.order === "withdraw") {               // остановлено на рубеже / отход с рубежа
      const back = g.order === "withdraw";
      return `<g transform="rotate(${brg.toFixed(0)})"><path d="M-18 4 V-2 Q-18 -6 -14 -6 H14 Q18 -6 18 -2 V4" fill="none" stroke="${c}" stroke-width="2.4"/>` +
             (back ? `<path d="M0 -6 Q0 -16 6 -13 Q9 -8 2 -2 V10" fill="none" stroke="${c}" stroke-width="1.6"/><path d="M2 14 L-1.5 8 L5.5 8 Z" fill="${c}"/>`
                   : `<path d="M0 -6 Q-1 -16 5 -15 Q10 -12 4 -8" fill="none" stroke="${c}" stroke-width="1.6"/><path d="M1 -6 L6 -10 L6 -5 Z" fill="${c}"/>`) + `</g>`;
    }
    if (g.order === "airhead" || g.vehicle === "heli") {                 // район высадки десанта (до высадки - пунктир)
      const d2 = g.order === "airhead" ? "" : ' stroke-dasharray="5 3"';
      return `<ellipse rx="${rx}" ry="${ry}" fill="none" stroke="${c}" stroke-width="2.2"${d2}/>${suVehicle("heli", c, -11, -2)}`;
    }
    if (["defend", "battle", "deployed", "refit"].includes(g.state) && g.order !== "reserve") {
      // расположение в обороне: замкнутый контур, по переднему краю - черточки к противнику, знаки техники на нём
      let t = "";
      for (let a = 205; a <= 335; a += 13) {
        const r = a * Math.PI / 180, x = rx * Math.cos(r), y = ry * Math.sin(r);
        const nx = Math.cos(r) / rx, ny = Math.sin(r) / ry, nl = Math.hypot(nx, ny);
        t += `<path d="M${x.toFixed(1)} ${y.toFixed(1)} l${(4 * nx / nl).toFixed(1)} ${(4 * ny / nl).toFixed(1)}" stroke="${c}" stroke-width="1.5"/>`;
      }
      const veh = g.vehicle === "foot" ? "" : suVehicle(g.vehicle, c, -9, -ry + 1, 0, .8) + suVehicle(g.vehicle, c, 9, -ry + 1, 0, .8);
      return `<g transform="rotate(${brg.toFixed(0)})"><ellipse rx="${rx}" ry="${ry}" fill="none" stroke="${c}" stroke-width="2.2"${dash}/>${t}${veh}</g>`;
    }
    // район, занимаемый подразделением (резерв, сосредоточение; пунктир - намечен к занятию): знак техники внутри
    return `<ellipse rx="${rx}" ry="${ry}" fill="none" stroke="${c}" stroke-width="2.2"${dash}/>${suVehicle(g.vehicle, c, -12, 0, brg, .85)}`;
  }
  // данные разведки о противнике: примерно - "?", только присутствие - "??" (знак бледнее, CSS fog-*)
  const fogMark = g => g.intel === "approx" ? "?" : g.intel === "presence" ? "??" : "";
  function unitSU(g, brg, dir) {
    const c = sideCol(g.side);
    return `<svg width="64" height="64" viewBox="-32 -32 64 64" class="su">${suShape(g, c, brg, dir)}</svg>` +
           `<div class="ulbl su" style="color:${ink(g)}">${esc(g.abbr)}${fogMark(g)}${g.supply < 1 ? " ⚠" : ""}</div>`;
  }

  // ---------- APP-6 (НАТО) ----------
  function unitNATO(g, friend) {
    const c = friend ? "#80e0ff" : "#ff8080", e = INK;
    const frame = friend ? `<rect x="-15" y="-10" width="30" height="20" fill="${c}" stroke="${e}" stroke-width="1.5"/>`
                         : `<path d="M0 -16 L16 0 L0 16 L-16 0 Z" fill="${c}" stroke="${e}" stroke-width="1.5"/>`;
    const sx = friend ? 15 : 9, sy = friend ? 10 : 7;
    let ic = "";
    if (g.branch === "tank") ic = `<ellipse rx="${sx * .6}" ry="${sy * .45}" fill="none" stroke="${e}" stroke-width="1.5"/>`;
    else if (g.branch === "mech") ic = `<path d="M${-sx} ${-sy} L${sx} ${sy} M${-sx} ${sy} L${sx} ${-sy}" stroke="${e}" stroke-width="1.3"/><ellipse rx="${sx * .6}" ry="${sy * .45}" fill="none" stroke="${e}" stroke-width="1.3"/>`;
    else if (g.branch === "airassault") ic = `<path d="M${-sx} ${-sy} L${sx} ${sy} M${-sx} ${sy} L${sx} ${-sy}" stroke="${e}" stroke-width="1.3"/><path d="M-6 ${-sy + 1} q3 4 6 0 q3 4 6 0" fill="none" stroke="${e}" stroke-width="1.3"/>`;
    else if (g.branch === "inf") ic = `<path d="M${-sx} ${-sy} L${sx} ${sy} M${-sx} ${sy} L${sx} ${-sy}" stroke="${e}" stroke-width="1.3"/>`;
    const ech = {I: "I", II: "II", III: "III", X: "X", XX: "XX"}[g.echelon] || "";
    const dash = g.state === "pending" ? ' stroke-dasharray="3 2"' : "";
    return `<svg width="64" height="64" viewBox="-32 -32 64 64" style="opacity:${g.state === "halted" ? .5 : 1}">` +
           `<g${dash}>${frame}</g>${ic}<text y="${friend ? -13 : -18}" text-anchor="middle" font-size="9" font-weight="700" fill="${e}">${ech}</text></svg>` +
           `<div class="ulbl" style="color:${INK}">${esc(g.abbr)}${fogMark(g)}${g.supply < 1 ? " ⚠" : ""}</div>`;
  }

  // ---------- ПВО, аэродромы, цели тыла ----------
  function sam(g, nato, friend) {
    const c = nato ? INK : sideCol(g.side);
    if (nato) {
      const fill = friend ? "#80e0ff" : "#ff8080";
      const frame = friend ? `<rect x="-11" y="-8" width="22" height="16" fill="${fill}" stroke="${c}" stroke-width="1.3"/>` : `<path d="M0 -12 L12 0 L0 12 L-12 0 Z" fill="${fill}" stroke="${c}" stroke-width="1.3"/>`;
      const icon = g.branch === "gci" ? `<path d="M-6 4 A7 7 0 0 1 6 -2 M0 1 L5 -5" fill="none" stroke="${c}" stroke-width="1.3"/>`
                                      : `<path d="M-8 6 A9 7 0 0 1 8 6" fill="none" stroke="${c}" stroke-width="1.3"/><path d="M0 4 L0 -6 M-2 -3 L0 -6 L2 -3" fill="none" stroke="${c}" stroke-width="1.3"/>`;
      return `<svg width="30" height="30" viewBox="-15 -15 30 30">${frame}${icon}</svg>`;
    }
    const k = g.side === "blue" ? BLUE : INK;   // наши ПВО - чёрным, противника - синим; знак всегда к верхнему обрезу
    if (g.branch === "gci")       // РЛС обнаружения воздушных целей (КРУ): треугольник на мачте, антенна
      return `<svg width="26" height="26" viewBox="-13 -13 26 26" fill="none" stroke="${k}" stroke-width="1.7"><path d="M-6 9 L0 -1 L6 9 Z M0 -1 V-9 M-5 -9 H5 M-6 -12 l2 2 M6 -12 l-2 2"/></svg>`;
    // пусковая установка зенитной ракеты: стрелка вверх, черточки - дальность (1 ближнего действия, 2 малой,
    // 3 средней); в кружке - батарея (позиция ЗРК)
    let t = "";
    for (let n = 0; n < (g.tier || 1); n++) t += `<path d="M-3.5 ${3 + 3 * n} H3.5"/>`;
    return `<svg width="28" height="28" viewBox="-14 -14 28 28" fill="none" stroke="${k}" stroke-width="1.7"><circle r="11.5"/>` +
           `<path d="M0 9 V-8"/><path d="M0 -10 L-2.8 -4 L2.8 -4 Z" fill="${k}"/>${t}</svg>`;
  }
  // аэродром - топографический знак (силуэт самолёта носом на север): действующий - залитый, закрытый или
  // потерянный - контурный (как "посадочная площадка") и перечёркнут; цвет - чей (авиация: наши красным)
  function airbase(b) {
    const off = b.state === "closed" || b.state === "lost";
    const c = sideCol(b.side);
    const plane = "M0 -10 C1 -10 1.3 -8 1.3 -6 L1.3 -2 L9.5 2.5 L9.5 4.2 L1.3 2 L1 6.5 L3.8 8.6 L3.8 9.8 L0 8.9 L-3.8 9.8 L-3.8 8.6 L-1 6.5 L-1.3 2 L-9.5 4.2 L-9.5 2.5 L-1.3 -2 L-1.3 -6 C-1.3 -8 -1 -10 0 -10 Z";
    return `<svg width="24" height="24" viewBox="-12 -12 24 24"><path d="${plane}" fill="${off ? "#fffdf6" : c}" stroke="${c}" stroke-width="${off ? 1.2 : .6}"/>` +
           (off ? `<path d="M-9 -9 L9 9 M9 -9 L-9 9" stroke="${c}" stroke-width="1.4"/>` : "") + `</svg>`;
  }
  // посадочная площадка вертолётов (передовая площадка, FARP): кружок с буквой "Т" цвета стороны, ярко, как аэродром;
  // занятая частью - заливкой, свободная - контуром; закрыта или потеряна - перечёркнута
  function farp(b) {
    const off = b.state === "closed" || b.state === "lost";
    const c = sideCol(b.side), used = b.units && b.units.length && !off;
    const t = used ? "#fffdf6" : c;
    return `<svg width="22" height="22" viewBox="-11 -11 22 22">` +
           `<circle r="8.5" fill="${used ? c : "#fffdf6"}" stroke="${c}" stroke-width="2"/>` +
           `<path d="M-4.2 -4.2 H4.2 M0 -4.2 V5" stroke="${t}" stroke-width="2.2"/>` +
           (off ? `<path d="M-8 -8 L8 8 M8 -8 L-8 8" stroke="${c}" stroke-width="1.6"/>` : "") + `</svg>`;
  }
  function target(o) {
    const dead = o.state === "lost" || o.damage >= 1;
    const c = o.role === "bridge" ? INK : sideCol(o.side);
    let body;
    if (o.role === "bridge")        // мост (топографический знак); разрушенный - перечёркнут
      body = `<path d="M-6 -8 L-3 -5 V5 L-6 8 M6 -8 L3 -5 V5 L6 8" fill="none" stroke="${c}" stroke-width="1.8"/>` +
             (dead ? `<path d="M-9 -7 L9 7 M9 -7 L-9 7" stroke="${c}" stroke-width="1.8"/>` : o.damage > 0 ? `<path d="M-9 -7 L9 7" stroke="${c}" stroke-width="1.8"/>` : "");
    else if (o.role === "factory")  // завод
      body = `<path d="M-9 8 L-9 -2 L-4 -5 L-4 -2 L1 -5 L1 -2 L4 -2 L4 -10 L7 -10 L7 8 Z" fill="#fffdf6" stroke="${c}" stroke-width="1.6"/>` +
             (dead ? `<path d="M-10 -10 L10 10 M10 -10 L-10 10" stroke="${c}" stroke-width="1.8"/>` : "");
    else {                          // склад (Г - горючего, Б - боеприпасов): квадрат, заливка - запас; отрезан - пунктир
      const lvl = o.stock == null ? 1 : Math.max(0, Math.min(1, o.stock));
      const h = 15 * lvl;
      body = `<rect x="-8" y="-8" width="16" height="16" fill="#fffdf6" stroke="${c}" stroke-width="1.8"${o.cut ? ' stroke-dasharray="3 2"' : ""}/>` +
             `<rect x="-7" y="${(7 - h).toFixed(1)}" width="14" height="${h.toFixed(1)}" fill="${c}" opacity=".25"/>` +
             `<text y="3.5" text-anchor="middle" font-size="9" font-style="italic" font-weight="700" fill="${c}">ГБ</text>` +
             (dead ? `<path d="M-10 -10 L10 10 M10 -10 L-10 10" stroke="${c}" stroke-width="1.8"/>` : "");
    }
    return `<svg width="24" height="24" viewBox="-12 -12 24 24" style="opacity:${o.checked ? 1 : .6}">${body}</svg>`;
  }
  function arrowHead(c) {
    return `<svg width="18" height="18" viewBox="-9 -9 18 18"><path d="M0 -8 L6 6 L0 2 L-6 6 Z" fill="${c}"/></svg>`;
  }

  // ---------- условные обозначения ----------
  function legend(nato) {
    const g = (side, state, branch) => ({side, state, branch, strength: .8, supply: 1, abbr: "", echelon: "XX"});
    const only = h => h.replace(/<div class="ulbl[\s\S]*$/, "").replace('width="64" height="64"', 'width="36" height="36"');
    const row = (pic, txt) => `<div class="lg"><span class="lgp">${pic}</span><span>${txt}</span></div>`;
    const line = (c1, c2) => `<svg width="30" height="10"><path d="M2 3 H28" stroke="${c1}" stroke-width="3"/><path d="M2 7 H28" stroke="${c2}" stroke-width="3"/></svg>`;
    const arrow = c => `<svg width="30" height="12"><path d="M2 6 H22" stroke="${c}" stroke-width="3"/><path d="M28 6 L20 1 L20 11 Z" fill="${c}"/></svg>`;
    if (nato) return row(only(unitNATO(g("blue", "defend", "tank"), true)), "свои: танковые (APP-6)") +
      row(only(unitNATO(g("red", "defend", "mech"), false)), "противник: мотопехота") +
      row(line(BLUE, RED), "линия фронта") + row(arrow(BLUE), "марш, наступление") +
      row(airbase({side: "blue", state: "open"}), "аэродром") + row(target({role: "depot", side: "blue", stock: .6, checked: true}), "склад (заливка - запас)") +
      row(target({role: "bridge", checked: true}), "мост");
    const G = (side, state, vehicle, order, echelon) => ({side, state, vehicle, order, echelon: echelon || "XX", supply: 1, abbr: ""});
    return `<div class="lg" style="color:#555">наши - красным (ПВО и надписи - чёрным), противник - синим</div>` +
      row(only(unitSU(G("red", "defend", "bmp"), 0)), "оборона: передний край к противнику, знаки БМП") +
      row(only(unitSU(G("red", "pending", "tank", "reserve"), 0)), "район, занимаемый частью (пунктир - намечен); ◇ танки") +
      row(only(unitSU(G("red", "march", "btr", null, "II"), 0, 0)), "колонна на марше (тб - три черты); ⬠ БТР") +
      row(only(unitSU(G("red", "battle", "tank", "attack"), 0)), "направление наступления") +
      row(only(unitSU(G("red", "halted", "tank"), 0)), "остановлена на рубеже") +
      row(`<span style="opacity:.55">${only(unitSU(G("blue", "defend", "tank"), 180))}</span>`, "противник по данным разведки: бледно - устарели (? - примерно, ?? - только присутствие), круг - где может быть") +
      row(line(RED, BLUE), "линия соприкосновения") +
      row(sam({side: "red", branch: "sam", tier: 2}, false) + sam({side: "red", branch: "gci"}, false), "ЗРК (черты - дальность), РЛС (КРУ)") +
      row(airbase({side: "red", state: "open"}) + airbase({side: "red", state: "closed"}), "аэродром; закрыт или потерян") +
      row(farp({side: "red", state: "open", units: ["x"]}) + farp({side: "red", state: "open", units: []}), "вертолётная площадка: занята частью; свободна") +
      row(target({role: "depot", side: "red", stock: .6, checked: true}), "склад (заливка - запас, пунктир - отрезан)") +
      row(target({role: "bridge", checked: true}) + target({role: "bridge", state: "lost", checked: true}), "мост, разрушенный мост") +
      `<div class="lg" style="color:#555">⚠ - часть без полного снабжения</div>`;
  }

  return {front, bearingTo, bearing, unitSU, unitNATO, sam, airbase, farp, target, arrowHead, legend, sideCol, RED, BLUE, INK};
})();
