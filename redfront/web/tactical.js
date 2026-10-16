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
      img.data[n * 4 + 3] = Math.round(40 * Math.min(1, 2.5 * fade));      // к краю - плавно на нет
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

  // ---------- советские знаки ----------
  // знак рода войск (маленький, рядом с подписью): танк - капсула, мотострелки - капсула с чертой (БМП/БТР),
  // десант - купол, пехота - флажок
  function suGlyph(branch, c) {
    if (branch === "tank") return `<rect x="-9" y="-4" width="18" height="8" rx="4" fill="none" stroke="${c}" stroke-width="2"/>`;
    if (branch === "mech") return `<rect x="-9" y="-4" width="18" height="8" rx="4" fill="none" stroke="${c}" stroke-width="2"/><line x1="0" y1="-4" x2="0" y2="4" stroke="${c}" stroke-width="2"/>`;
    if (branch === "airassault") return `<path d="M-8 3 A8 8 0 0 1 8 3 Z" fill="none" stroke="${c}" stroke-width="2"/><path d="M-8 3 L0 9 L8 3 M0 3 L0 9" fill="none" stroke="${c}" stroke-width="1.4"/>`;
    return `<path d="M-5 6 L-5 -6 L6 -3 L-5 0" fill="none" stroke="${c}" stroke-width="2"/>`;
  }
  // главный знак: оборона (дуга к противнику), бой (дуга + разрыв), район сосредоточения (овал), марш (стрелка - на маршруте)
  function suShape(g, c, brg) {
    const w = 2 + 2.5 * g.strength, dash = g.state === "pending" ? ' stroke-dasharray="4 3"' : "";
    if (["defend", "battle", "halted", "refit", "deployed"].includes(g.state) && g.order !== "reserve") {
      const blast = g.state === "battle" ? `<path d="M0 -27 l2 4 4 -2 -1 4 4 1 -4 2 2 4 -4 -1 -1 4 -2 -3 -3 3 0 -4 -4 0 3 -3 -3 -3 4 0 z" fill="#f2b705" stroke="${INK}" stroke-width=".6"/>` : "";
      return `<g transform="rotate(${brg.toFixed(0)})"><path d="M-20 4 A24 24 0 0 1 20 4" fill="none" stroke="${c}" stroke-width="${w.toFixed(1)}"${dash} stroke-linecap="round"/>${blast}</g>`;
    }
    return `<ellipse cx="0" cy="0" rx="17" ry="10" fill="none" stroke="${c}" stroke-width="${(w * .8).toFixed(1)}"${dash}/>`;
  }
  function unitSU(g, brg) {
    const c = sideCol(g.side);
    const op = g.state === "halted" ? .5 : 1;
    return `<svg width="64" height="64" viewBox="-32 -32 64 64" style="opacity:${op}">${suShape(g, c, brg)}` +
           `<g transform="translate(0,0)">${suGlyph(g.branch, c)}</g></svg>` +
           `<div class="ulbl" style="color:${c}">${esc(g.abbr)}${g.supply < 1 ? " ⚠" : ""}</div>`;
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
           `<div class="ulbl" style="color:${INK}">${esc(g.abbr)}${g.supply < 1 ? " ⚠" : ""}</div>`;
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
    if (g.branch === "gci")       // КРУ: антенна-"тарелка"
      return `<svg width="26" height="26" viewBox="-13 -13 26 26"><path d="M-8 2 A9 9 0 0 1 4 -8 Z" fill="none" stroke="${c}" stroke-width="2"/><path d="M-2 -3 L-2 8 M-6 8 L2 8" stroke="${c}" stroke-width="2"/></svg>`;
    // ЗРК: ракета на пусковой (стрелка вверх над полудугой)
    return `<svg width="26" height="26" viewBox="-13 -13 26 26"><path d="M-9 8 A9 6 0 0 1 9 8" fill="none" stroke="${c}" stroke-width="2"/><path d="M0 6 L0 -9 M-3.5 -5 L0 -10 L3.5 -5" fill="none" stroke="${c}" stroke-width="2"/></svg>`;
  }
  function airbase(b) {
    const c = b.state === "lost" || b.state === "closed" ? GREY : sideCol(b.side);
    const x = b.state === "closed" || b.state === "lost" ? `<path d="M-9 -9 L9 9 M9 -9 L-9 9" stroke="${GREY}" stroke-width="1.6"/>` : "";
    return `<svg width="26" height="26" viewBox="-13 -13 26 26"><circle r="10" fill="#fffdf6" stroke="${c}" stroke-width="2"/>` +
           `<path d="M0 -7 L1.4 -2 L7 1 L7 2.6 L1.4 1 L1 5 L3 6.6 L3 7.6 L0 6.8 L-3 7.6 L-3 6.6 L-1 5 L-1.4 1 L-7 2.6 L-7 1 L-1.4 -2 Z" fill="${c}"/>${x}</svg>`;
  }
  function target(o) {
    const dead = o.state === "lost" || o.damage >= 1;
    const c = dead ? GREY : o.role === "bridge" ? INK : sideCol(o.side);
    const dmg = o.damage > 0 && !dead ? `<path d="M-9 -9 L9 9" stroke="${RED}" stroke-width="${(1 + 3 * o.damage).toFixed(1)}" opacity=".85"/>` : "";
    const x = dead ? `<path d="M-9 -9 L9 9 M9 -9 L-9 9" stroke="${INK}" stroke-width="2"/>` : "";
    let body;
    if (o.role === "bridge") body = `<path d="M-8 -7 Q-4 0 -8 7 M8 -7 Q4 0 8 7" fill="none" stroke="${c}" stroke-width="2.2"/>`;
    else if (o.role === "factory") body = `<path d="M-9 8 L-9 -2 L-4 -5 L-4 -2 L1 -5 L1 -2 L4 -2 L4 -10 L7 -10 L7 8 Z" fill="#fffdf6" stroke="${c}" stroke-width="1.8"/>`;
    else {                                         // склад: "домик" с заливкой - запас
      const lvl = o.stock == null ? 1 : Math.max(0, Math.min(1, o.stock));
      const h = 13 * lvl;
      body = `<path d="M-9 8 L-9 -3 L0 -9 L9 -3 L9 8 Z" fill="#fffdf6" stroke="${c}" stroke-width="1.8"/>` +
             `<rect x="-7.5" y="${(6.5 - h).toFixed(1)}" width="15" height="${h.toFixed(1)}" fill="${c}" opacity=".55"/>` +
             (o.cut ? `<circle cx="8" cy="-8" r="3" fill="#f2b705" stroke="${INK}" stroke-width=".8"/>` : "");
    }
    return `<svg width="24" height="24" viewBox="-12 -12 24 24" style="opacity:${o.checked ? 1 : .6}">${body}${dmg}${x}</svg>`;
  }
  function arrowHead(c) {
    return `<svg width="18" height="18" viewBox="-9 -9 18 18"><path d="M0 -8 L6 6 L0 2 L-6 6 Z" fill="${c}"/></svg>`;
  }

  // ---------- условные обозначения ----------
  function legend(nato) {
    const g = (side, state, branch) => ({side, state, branch, strength: .8, supply: 1, abbr: "", echelon: "XX"});
    const only = h => h.replace(/<div class="ulbl"[\s\S]*$/, "").replace('width="64" height="64"', 'width="34" height="34"');
    const row = (pic, txt) => `<div class="lg"><span class="lgp">${pic}</span><span>${txt}</span></div>`;
    const line = (c1, c2) => `<svg width="30" height="10"><path d="M2 3 H28" stroke="${c1}" stroke-width="3"/><path d="M2 7 H28" stroke="${c2}" stroke-width="3"/></svg>`;
    const arrow = c => `<svg width="30" height="12"><path d="M2 6 H22" stroke="${c}" stroke-width="3"/><path d="M28 6 L20 1 L20 11 Z" fill="${c}"/></svg>`;
    if (nato) return row(only(unitNATO(g("blue", "defend", "tank"), true)), "свои: танковые (APP-6)") +
      row(only(unitNATO(g("red", "defend", "mech"), false)), "противник: мотопехота") +
      row(line(BLUE, RED), "линия фронта") + row(arrow(BLUE), "марш, наступление") +
      row(airbase({side: "blue", state: "open"}), "аэродром") + row(target({role: "depot", side: "blue", stock: .6, checked: true}), "склад (заливка - запас)") +
      row(target({role: "bridge", checked: true}), "мост");
    return row(only(unitSU(g("red", "defend", "tank"), 0)), "оборона (дуга к противнику); знак - танковые") +
      row(only(unitSU(g("red", "battle", "mech"), 0)), "ведёт бой; знак - мотострелки") +
      row(only(unitSU(g("blue", "pending", "tank"), 0)), "противник: район сосредоточения, марш") +
      row(arrow(RED), "направление марша, наступления") +
      row(line(RED, BLUE), "передний край: свои / противник") +
      row(sam({side: "blue", branch: "sam"}, false), "ЗРК (пунктир - зона поражения)") +
      row(airbase({side: "red", state: "open"}), "аэродром") +
      row(target({role: "depot", side: "red", stock: .6, checked: true}), "склад, заливка - запас") +
      row(target({role: "bridge", checked: true}), "мост") +
      `<div class="lg" style="color:#666">⚠ - часть без полного снабжения</div>`;
  }

  return {front, bearingTo, bearing, unitSU, unitNATO, sam, airbase, target, arrowHead, legend, sideCol, RED, BLUE, INK};
})();
