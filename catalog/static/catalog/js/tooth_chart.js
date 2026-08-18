/* Интерактивная зубная карта FDI для админки кейса.
   Управляет тремя нативными полями формы:
     #id_tooth_scope  (select: teeth | arch | full_mouth)
     #id_teeth        (JSON-массив, напр. ["46","47"])   — хранение без точки
     #id_arches       (JSON-массив: ["upper"] / ["lower"] / оба)
   Нативные поля прячутся, а сабмит формы идёт через них как обычно.
   Производные фасеты (сторона/группа/прикус) считает сервер в Case.save();
   здесь показывается лишь превью для удобства. */
(function () {
  "use strict";

  var PERM_UPPER = ["18","17","16","15","14","13","12","11","21","22","23","24","25","26","27","28"];
  var PERM_LOWER = ["48","47","46","45","44","43","42","41","31","32","33","34","35","36","37","38"];
  var PRIM_UPPER = ["55","54","53","52","51","61","62","63","64","65"];
  var PRIM_LOWER = ["85","84","83","82","81","71","72","73","74","75"];
  var ARCH_LABEL = { upper: "Верхняя челюсть", lower: "Нижняя челюсть" };

  function fdi(t) { return t[0] + "." + t[1]; }
  function parseList(v) { try { var a = JSON.parse(v || "[]"); return Array.isArray(a) ? a : []; } catch (e) { return []; } }
  function toggle(arr, v) { var i = arr.indexOf(v); if (i < 0) arr.push(v); else arr.splice(i, 1); return arr; }

  function toothFacets(teeth) {
    var QA = {1:"upper",2:"upper",5:"upper",6:"upper",3:"lower",4:"lower",7:"lower",8:"lower"};
    var QS = {1:"right",4:"right",5:"right",8:"right",2:"left",3:"left",6:"left",7:"left"};
    var arches = {}, sides = {}, groups = {}, dent = {};
    teeth.forEach(function (t) {
      var q = +t[0], p = +t[1], primary = q >= 5;
      arches[QA[q]] = 1; sides[QS[q]] = 1; dent[primary ? "молочные" : "постоянные"] = 1;
      if (p <= 2) groups["резцы"] = 1; else if (p === 3) groups["клыки"] = 1;
      else if (primary) groups["молочные моляры"] = 1;
      else if (p <= 5) groups["премоляры"] = 1; else groups["моляры"] = 1;
    });
    var ru = { upper: "верхняя", lower: "нижняя", right: "справа", left: "слева" };
    function keys(o) { return Object.keys(o).map(function (k) { return ru[k] || k; }); }
    return keys(dent).concat(keys(arches), keys(sides), Object.keys(groups));
  }

  function chip(text, active, disabled) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "tc-chip" + (active ? " tc-on" : "") + (disabled ? " tc-dis" : "");
    b.textContent = text;
    if (disabled) b.disabled = true;
    return b;
  }

  function enhance(scopeSel) {
    if (scopeSel.dataset.tcBound) return;
    scopeSel.dataset.tcBound = "1";
    var teethInp = document.getElementById("id_teeth");
    var archesInp = document.getElementById("id_arches");
    if (!teethInp || !archesInp) return;

    var state = {
      scope: scopeSel.value || "teeth",
      teeth: parseList(teethInp.value),
      arches: parseList(archesInp.value),
    };
    // какой ряд показывать: молочные, если выбраны только молочные зубы
    var hasPerm = state.teeth.some(function (t) { return +t[0] <= 4; });
    var hasPrim = state.teeth.some(function (t) { return +t[0] >= 5; });
    var ui = { dent: (hasPrim && !hasPerm) ? "prim" : "perm" };

    function sync() {
      scopeSel.value = state.scope;
      teethInp.value = JSON.stringify(state.teeth);
      archesInp.value = JSON.stringify(state.arches);
    }

    var box = document.createElement("div");
    box.className = "tc-box";

    function render() {
      box.innerHTML = "";
      var locked = state.scope !== "teeth";

      // 1. охват
      var scopeRow = document.createElement("div");
      scopeRow.className = "tc-row";
      [["teeth", "Отдельные зубы"], ["arch", "Зубной ряд целиком"],
       ["full_mouth", "Обе челюсти (полная реабилитация)"]].forEach(function (s) {
        var c = chip(s[1], state.scope === s[0], false);
        c.addEventListener("click", function () {
          state.scope = s[0];
          if (s[0] !== "teeth") state.teeth = [];
          if (s[0] !== "arch") state.arches = [];
          sync(); render();
        });
        scopeRow.appendChild(c);
      });
      box.appendChild(scopeRow);

      // 2. челюсти (для scope=arch)
      if (state.scope === "arch") {
        var archRow = document.createElement("div");
        archRow.className = "tc-row";
        ["upper", "lower"].forEach(function (a) {
          var c = chip(ARCH_LABEL[a], state.arches.indexOf(a) >= 0, false);
          c.addEventListener("click", function () { toggle(state.arches, a); sync(); render(); });
          archRow.appendChild(c);
        });
        box.appendChild(archRow);
      }

      // 3. описание full_mouth
      if (state.scope === "full_mouth") {
        var p = document.createElement("p");
        p.className = "tc-note";
        p.textContent = "Комплексное восстановление всех или почти всех зубов обеих челюстей, "
          + "обычно с изменением высоты прикуса. Типичные показания — выраженная стираемость, "
          + "множественное отсутствие зубов, тяжёлая эрозия.";
        box.appendChild(p);
      }

      // 4. постоянные / молочные
      var dentRow = document.createElement("div");
      dentRow.className = "tc-row";
      [["perm", "Постоянные"], ["prim", "Молочные"]].forEach(function (d) {
        var c = chip(d[1], ui.dent === d[0], locked);
        if (!locked) c.addEventListener("click", function () { ui.dent = d[0]; render(); });
        dentRow.appendChild(c);
      });
      if (state.scope === "teeth" && state.teeth.length) {
        var clr = document.createElement("button");
        clr.type = "button"; clr.className = "tc-clear"; clr.textContent = "Снять все";
        clr.addEventListener("click", function () { state.teeth = []; sync(); render(); });
        dentRow.appendChild(clr);
      }
      box.appendChild(dentRow);

      // 5. сетка зубов
      var grid = document.createElement("div");
      grid.className = "tc-grid" + (locked ? " tc-locked" : "");
      if (locked) {
        var msg = document.createElement("div");
        msg.className = "tc-lockmsg";
        msg.textContent = "Выбор отдельных зубов отключён — задан охват «"
          + (state.scope === "arch" ? "зубной ряд целиком" : "обе челюсти") + "»";
        grid.appendChild(msg);
      }
      var rows = ui.dent === "perm" ? [PERM_UPPER, PERM_LOWER] : [PRIM_UPPER, PRIM_LOWER];
      rows.forEach(function (row) {
        var r = document.createElement("div");
        r.className = "tc-teethrow";
        row.forEach(function (t, i) {
          var on = state.teeth.indexOf(t) >= 0;
          var b = document.createElement("button");
          b.type = "button";
          b.className = "tc-tooth" + (on ? " tc-on" : "") + (i === row.length / 2 ? " tc-gap" : "");
          b.textContent = fdi(t);
          b.disabled = locked;
          if (!locked) b.addEventListener("click", function () { toggle(state.teeth, t); sync(); render(); });
          r.appendChild(b);
        });
        grid.appendChild(r);
      });
      box.appendChild(grid);

      // 6. превью фасетов
      if (state.scope === "teeth" && state.teeth.length) {
        var pf = document.createElement("div");
        pf.className = "tc-facets";
        pf.innerHTML = '<div class="tc-facets-h">ПРОИЗВОДНЫЕ ФАСЕТЫ (считает сервер)</div>'
          + '<div class="tc-facets-t">' + state.teeth.map(fdi).join(", ") + "</div>"
          + '<div class="tc-facets-d">' + toothFacets(state.teeth).join(" · ") + "</div>";
        box.appendChild(pf);
      }
    }

    // прячем нативные поля, вставляем виджет
    function hideRow(input) {
      var row = input.closest(".form-row") || input.closest(".fieldBox") || input.parentNode;
      if (row) row.style.display = "none";
    }
    var anchor = scopeSel.closest(".form-row") || scopeSel.closest(".fieldBox") || scopeSel.parentNode;
    anchor.parentNode.insertBefore(box, anchor);
    hideRow(scopeSel); hideRow(teethInp); hideRow(archesInp);

    sync(); render();
  }

  function init() {
    var sel = document.getElementById("id_tooth_scope");
    if (sel) enhance(sel);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
