/* Редактор группировки вариантов — одно окно.
 * Параметры правятся локально и сохраняются кнопкой «Сохранить».
 * Порядок задаётся перетаскиванием (за ручку ⠿):
 *   — уровни: порядок разделов;
 *   — товары: порядок внутри раздела и перенос между разделами (= смена уровня).
 * Структурные действия (добавить/убрать товар, добавить/удалить уровень) — сразу.
 * Без зависимостей. */
(function () {
  "use strict";
  var root = document.getElementById("group-editor");
  if (!root) return;

  var BASE = root.getAttribute("data-base") || location.pathname;
  if (BASE.slice(-1) !== "/") BASE += "/";
  var tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
  var CSRF = tokenInput ? tokenInput.value : "";

  var statusEl = document.createElement("div");
  statusEl.className = "ge-status";
  document.body.appendChild(statusEl);
  var statusTimer = null;
  function status(msg, ok) {
    statusEl.textContent = msg;
    statusEl.className = "ge-status show " + (ok ? "ok" : "err");
    clearTimeout(statusTimer);
    statusTimer = setTimeout(function () { statusEl.className = "ge-status"; }, 1800);
  }

  function api(path, opts) {
    opts = opts || {};
    var headers = { "X-CSRFToken": CSRF };
    if (opts.body) headers["Content-Type"] = "application/json";
    return fetch(BASE + path, {
      method: opts.method || "GET", headers: headers, credentials: "same-origin",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.error || ("Ошибка " + r.status));
        return data;
      });
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function debounce(fn, ms) {
    var t;
    return function () { var a = arguments, self = this; clearTimeout(t); t = setTimeout(function () { fn.apply(self, a); }, ms || 300); };
  }
  function byId(arr, id) { return arr.filter(function (x) { return x.id === id; })[0]; }
  function byOrder(a, b) { return (a.order - b.order) || 0; }
  function byMemberOrder(a, b) {
    return (a.group_order - b.group_order) || String(a.name).localeCompare(String(b.name), "ru");
  }

  var state = { group: {}, levels: [], members: [] };
  var dirty = false;
  var selected = {};   // id -> name; выбранные для добавления (копится между поисками)
  var resultsEl = null;

  function markDirty() {
    dirty = true;
    var b = document.getElementById("ge-save"); if (b) b.disabled = false;
    var d = document.getElementById("ge-dirty"); if (d) d.textContent = "есть несохранённые изменения";
  }
  function selectedCount() { return Object.keys(selected).length; }
  function updateSelBar() {
    var bar = document.getElementById("ge-selbar"); if (bar) bar.hidden = selectedCount() === 0;
    var c = document.getElementById("ge-selcount"); if (c) c.textContent = "Выбрано: " + selectedCount();
  }

  // ---------- разметка ----------
  function memberRow(m) {
    return '<tr data-id="' + m.id + '">' +
      '<td class="ge-griptd"><span class="ge-grip" title="Перетащите">\u28ff</span></td>' +
      '<td><div class="ge-pname">' + esc(m.name) + "</div>" +
        (m.sku ? '<div class="ge-psku">Артикул: ' + esc(m.sku) + "</div>" : "") + "</td>" +
      '<td><input type="text" class="ge-m" data-f="variant_label" value="' + esc(m.variant_label) +
        '" placeholder="подпись на кнопке"></td>' +
      '<td class="ge-actcell"><button type="button" class="ge-del" data-act="remove">убрать</button></td>' +
      "</tr>";
  }
  function levelSection(levelId, title) {
    var members = state.members.filter(function (m) { return m.group_level === levelId; }).sort(byMemberOrder);
    var rows = members.length
      ? members.map(memberRow).join("")
      : '<tr class="ge-ph"><td colspan="4" class="ge-empty">— перетащите сюда товары —</td></tr>';
    return '<div class="ge-lgroup"><h3 class="ge-section-title">' + esc(title) + "</h3>" +
      '<table class="ge-table"><tbody data-level="' + (levelId == null ? "" : levelId) + '">' + rows + "</tbody></table></div>";
  }
  function levelItem(l) {
    return '<li data-id="' + l.id + '">' +
      '<span class="ge-grip" title="Перетащите">\u28ff</span>' +
      '<input type="text" class="ge-lf ge-lname" data-f="name" value="' + esc(l.name) + '">' +
      '<button type="button" class="ge-del" data-act="del-level">удалить</button>' +
      "</li>";
  }

  function render() {
    var levelsList = state.levels.length
      ? '<ul class="ge-levels-list">' + state.levels.slice().sort(byOrder).map(levelItem).join("") + "</ul>"
      : '<div class="ge-empty">Уровней пока нет. Добавьте хотя бы один — это разделы переключателя на витрине.</div>';

    var sections = state.levels.slice().sort(byOrder).map(function (l) { return levelSection(l.id, l.name); }).join("");
    sections += levelSection(null, "Без уровня");

    root.innerHTML =
      '<div class="ge-savebar"><button type="button" id="ge-save" class="button default"' +
        (dirty ? "" : " disabled") + ">Сохранить изменения</button>" +
        '<span id="ge-dirty" class="ge-dirty">' + (dirty ? "есть несохранённые изменения" : "") + "</span></div>" +

      '<div class="ge-card ge-namebox"><h2>Серия (внутреннее имя)</h2>' +
        '<div class="ge-hint">Видно только в админке. На витрине показываются уровни и подписи вариантов.</div>' +
        '<input type="text" id="ge-name" value="' + esc(state.group.name) + '"></div>' +

      '<div class="ge-card"><h2>Уровни (разделы переключателя)</h2>' +
        '<div class="ge-hint">Публичные названия разделов. Порядок — перетаскиванием за \u28ff. Удаление уровня снимает его с товаров.</div>' +
        levelsList +
        '<button type="button" class="button" id="ge-add-level">+ Добавить уровень</button></div>' +

      '<div class="ge-card"><h2>Участники (по разделам)</h2>' +
        '<div class="ge-hint">Перетаскивайте товары за \u28ff: внутри раздела — порядок, между разделами — смена уровня. Подпись — текст на кнопке варианта.</div>' +
        '<div class="ge-addbox"><div class="ge-hint">Добавить товары (ищутся только те, что не состоят ни в одной серии). Отметьте нужные галочками и нажмите «Добавить выбранные».</div>' +
          '<div class="ge-search"><input type="text" id="ge-search" placeholder="Поиск по названию или артикулу…" autocomplete="off"><div class="ge-results" hidden></div></div>' +
          '<div class="ge-selbar" id="ge-selbar"' + (selectedCount() ? "" : " hidden") + ">" +
            '<span class="ge-selcount" id="ge-selcount">Выбрано: ' + selectedCount() + "</span>" +
            '<button type="button" class="button default" id="ge-add-selected">Добавить выбранные</button>' +
            '<button type="button" class="ge-linkbtn" id="ge-clear-sel">сбросить</button>' +
          "</div>" +
        "</div>" +
        sections +
      "</div>";

    wire();
  }

  // ---------- сохранение ----------
  function commit() {
    return api("save/", {
      method: "POST",
      body: {
        name: state.group.name,
        levels: state.levels.map(function (l) { return { id: l.id, name: l.name, order: l.order }; }),
        members: state.members.map(function (m) {
          return { id: m.id, variant_label: m.variant_label, group_level: m.group_level, group_order: m.group_order };
        }),
      },
    });
  }
  function structural(fn) {
    var pre = dirty ? commit() : Promise.resolve();
    return pre.then(fn).then(loadState).catch(function (e) { status(e.message, false); });
  }

  // ---------- drag-and-drop ----------
  function dragAfter(container, sel, y) {
    var els = Array.prototype.slice.call(container.querySelectorAll(sel + ":not(.ge-dragging)"));
    var closest = { offset: -Infinity, el: null };
    els.forEach(function (el) {
      var box = el.getBoundingClientRect();
      var offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) closest = { offset: offset, el: el };
    });
    return closest.el;
  }

  function setupMembersDnD() {
    var dragging = null;
    root.querySelectorAll("tbody[data-level] tr[data-id]").forEach(function (tr) {
      var grip = tr.querySelector(".ge-grip");
      if (grip) grip.addEventListener("mousedown", function () { tr.setAttribute("draggable", "true"); });
      tr.addEventListener("dragstart", function (e) {
        dragging = tr; tr.classList.add("ge-dragging");
        e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text", "");
      });
      tr.addEventListener("dragend", function () {
        tr.classList.remove("ge-dragging"); tr.setAttribute("draggable", "false"); dragging = null; commitMembers();
      });
    });
    root.querySelectorAll("tbody[data-level]").forEach(function (tb) {
      tb.addEventListener("dragover", function (e) {
        if (!dragging) return;
        e.preventDefault();
        var after = dragAfter(tb, "tr[data-id]", e.clientY);
        if (after == null) tb.appendChild(dragging); else tb.insertBefore(dragging, after);
      });
    });
  }
  function commitMembers() {
    root.querySelectorAll("tbody[data-level]").forEach(function (tb) {
      var lv = tb.getAttribute("data-level");
      var levelId = lv ? parseInt(lv, 10) : null;
      var idx = 0;
      tb.querySelectorAll("tr[data-id]").forEach(function (tr) {
        var m = byId(state.members, parseInt(tr.getAttribute("data-id"), 10));
        if (m) { m.group_level = levelId; m.group_order = idx++; }
      });
    });
    markDirty(); render();
  }

  function setupLevelsDnD() {
    var list = root.querySelector(".ge-levels-list");
    if (!list) return;
    var dragging = null;
    list.querySelectorAll("li").forEach(function (li) {
      var grip = li.querySelector(".ge-grip");
      if (grip) grip.addEventListener("mousedown", function () { li.setAttribute("draggable", "true"); });
      li.addEventListener("dragstart", function (e) {
        dragging = li; li.classList.add("ge-dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text", "");
      });
      li.addEventListener("dragend", function () {
        li.classList.remove("ge-dragging"); li.setAttribute("draggable", "false"); dragging = null; commitLevels();
      });
    });
    list.addEventListener("dragover", function (e) {
      if (!dragging) return;
      e.preventDefault();
      var after = dragAfter(list, "li", e.clientY);
      if (after == null) list.appendChild(dragging); else list.insertBefore(dragging, after);
    });
  }
  function commitLevels() {
    var idx = 0;
    root.querySelectorAll(".ge-levels-list li").forEach(function (li) {
      var l = byId(state.levels, parseInt(li.getAttribute("data-id"), 10));
      if (l) l.order = idx++;
    });
    markDirty(); render();
  }

  // ---------- события ----------
  function wire() {
    document.getElementById("ge-save").addEventListener("click", function () {
      commit().then(function () { status("Сохранено", true); loadState(); })
        .catch(function (e) { status(e.message, false); });
    });

    var nameInput = document.getElementById("ge-name");
    nameInput.addEventListener("input", function () { state.group.name = nameInput.value; markDirty(); });

    root.querySelectorAll(".ge-levels-list li").forEach(function (li) {
      var id = parseInt(li.getAttribute("data-id"), 10);
      var lvl = byId(state.levels, id);
      var nameInp = li.querySelector("input.ge-lname");
      if (nameInp) nameInp.addEventListener("input", function () { if (lvl) { lvl.name = nameInp.value; markDirty(); } });
      var del = li.querySelector('[data-act="del-level"]');
      if (del) del.addEventListener("click", function () {
        if (!confirm("Удалить уровень? Товары этого уровня останутся без уровня.")) return;
        structural(function () { return api("level/", { method: "POST", body: { action: "delete", level_id: id } }); })
          .then(function () { status("Уровень удалён", true); });
      });
    });
    document.getElementById("ge-add-level").addEventListener("click", function () {
      structural(function () { return api("level/", { method: "POST", body: { action: "add", name: "Новый уровень" } }); })
        .then(function () { status("Уровень добавлен", true); });
    });

    root.querySelectorAll("tbody[data-level] tr[data-id]").forEach(function (tr) {
      var id = parseInt(tr.getAttribute("data-id"), 10);
      var m = byId(state.members, id);
      var labelInp = tr.querySelector("input.ge-m");
      if (labelInp) labelInp.addEventListener("input", function () { if (m) { m.variant_label = labelInp.value; markDirty(); } });
      var rm = tr.querySelector('[data-act="remove"]');
      if (rm) rm.addEventListener("click", function () {
        if (!confirm("Убрать товар из серии?")) return;
        structural(function () { return api("member/", { method: "POST", body: { action: "remove", product_id: id } }); })
          .then(function () { status("Убрано", true); });
      });
    });

    var search = document.getElementById("ge-search");
    resultsEl = root.querySelector(".ge-results");
    var doSearch = debounce(function () {
      var q = search.value.trim();
      if (q.length < 2) { resultsEl.hidden = true; resultsEl.innerHTML = ""; return; }
      api("search/?q=" + encodeURIComponent(q)).then(function (d) {
        if (!d.results.length) {
          resultsEl.innerHTML = '<div class="ge-noresult">Ничего не найдено</div>';
        } else {
          resultsEl.innerHTML = d.results.map(function (r) {
            var checked = selected[r.id] ? " checked" : "";
            return '<label class="ge-result" data-id="' + r.id + '"><input type="checkbox"' + checked + ">" +
              '<span class="ge-rname">' + esc(r.name) + "</span>" +
              (r.sku ? '<span class="ge-rsku">' + esc(r.sku) + "</span>" : "") + "</label>";
          }).join("");
        }
        resultsEl.hidden = false;
      }).catch(function (e) { status(e.message, false); });
    }, 300);
    search.addEventListener("input", doSearch);
    resultsEl.addEventListener("change", function (e) {
      var lab = e.target.closest(".ge-result"); if (!lab) return;
      var id = parseInt(lab.getAttribute("data-id"), 10);
      if (e.target.checked) selected[id] = lab.querySelector(".ge-rname").textContent;
      else delete selected[id];
      updateSelBar();
    });
    document.getElementById("ge-add-selected").addEventListener("click", function () {
      var ids = Object.keys(selected).map(Number);
      if (!ids.length) return;
      var pre = dirty ? commit() : Promise.resolve();
      pre.then(function () { return api("member/", { method: "POST", body: { action: "add", product_ids: ids } }); })
        .then(function (res) {
          selected = {};
          status("Добавлено: " + (res.added || 0) + (res.skipped ? (", пропущено: " + res.skipped) : ""), true);
          return loadState();
        })
        .catch(function (e) { status(e.message, false); });
    });
    document.getElementById("ge-clear-sel").addEventListener("click", function () {
      selected = {}; updateSelBar();
      if (resultsEl) resultsEl.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = false; });
    });

    setupLevelsDnD();
    setupMembersDnD();
  }

  // сброс draggable у прерванных перетаскиваний + предупреждение об уходе
  document.addEventListener("mouseup", function () {
    root.querySelectorAll('[draggable="true"]').forEach(function (el) { el.setAttribute("draggable", "false"); });
  });
  document.addEventListener("click", function (e) {
    if (resultsEl && !e.target.closest(".ge-search")) resultsEl.hidden = true;
  });
  window.addEventListener("beforeunload", function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });

  function loadState() {
    return api("state/").then(function (d) {
      state = { group: d.group || {}, levels: d.levels || [], members: d.members || [] };
      dirty = false; render();
    }).catch(function (e) { root.textContent = "Не удалось загрузить редактор: " + e.message; });
  }

  loadState();
})();
