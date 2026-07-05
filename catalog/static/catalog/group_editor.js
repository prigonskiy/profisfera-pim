/* Редактор группировки вариантов — одно окно.
 * Параметры правятся локально и сохраняются кнопкой «Сохранить». Структурные
 * действия (добавить/убрать товар, добавить/удалить уровень) — сразу.
 * Участники сгруппированы по уровням: порядок разделов задаётся в «Уровнях»,
 * порядок внутри раздела — полем «Порядок» у товара. Без зависимостей. */
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
      method: opts.method || "GET",
      headers: headers,
      credentials: "same-origin",
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
    return function () {
      var a = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, a); }, ms || 300);
    };
  }

  var state = { group: {}, levels: [], members: [] };
  var dirty = false;
  var resultsEl = null;

  function markDirty() {
    dirty = true;
    var b = document.getElementById("ge-save");
    if (b) b.disabled = false;
    var d = document.getElementById("ge-dirty");
    if (d) d.textContent = "есть несохранённые изменения";
  }

  function levelOptions(selected) {
    var opts = '<option value="">— без уровня —</option>';
    state.levels.slice().sort(byOrder).forEach(function (l) {
      opts += '<option value="' + l.id + '"' + (l.id === selected ? " selected" : "") +
        ">" + esc(l.name) + "</option>";
    });
    return opts;
  }
  function byOrder(a, b) { return (a.order - b.order) || 0; }
  function byMemberOrder(a, b) {
    return (a.group_order - b.group_order) || String(a.name).localeCompare(String(b.name), "ru");
  }

  function memberRow(m) {
    return '<tr data-id="' + m.id + '">' +
      '<td><div class="ge-pname">' + esc(m.name) + "</div>" +
        (m.sku ? '<div class="ge-psku">Артикул: ' + esc(m.sku) + "</div>" : "") + "</td>" +
      '<td><input type="text" class="ge-m" data-f="variant_label" value="' + esc(m.variant_label) +
        '" placeholder="подпись на кнопке"></td>' +
      '<td class="ge-lvl"><select class="ge-m ge-movelvl" data-f="group_level">' +
        levelOptions(m.group_level) + "</select></td>" +
      '<td class="ge-num"><input type="number" min="0" class="ge-m" data-f="group_order" value="' +
        (m.group_order || 0) + '"></td>' +
      '<td><button type="button" class="ge-del" data-act="remove">убрать</button></td>' +
      "</tr>";
  }

  function levelSection(levelId, title) {
    var members = state.members.filter(function (m) { return m.group_level === levelId; }).sort(byMemberOrder);
    var rows = members.length
      ? members.map(memberRow).join("")
      : '<tr><td colspan="5" class="ge-empty">— в этом разделе пока нет товаров —</td></tr>';
    return '<div class="ge-lgroup"><h3 class="ge-section-title">' + esc(title) + "</h3>" +
      '<table class="ge-table"><thead><tr><th>Товар</th><th>Подпись варианта</th>' +
      '<th>Уровень (переместить)</th><th class="ge-num">Порядок в разделе</th><th></th></tr></thead>' +
      "<tbody>" + rows + "</tbody></table></div>";
  }

  function render() {
    var levelsItems = state.levels.slice().sort(byOrder).map(function (l) {
      return '<li data-id="' + l.id + '">' +
        '<input type="text" class="ge-lf ge-lname" data-f="name" value="' + esc(l.name) + '">' +
        '<input type="number" min="0" class="ge-lf ge-lorder" data-f="order" value="' + (l.order || 0) + '" title="Порядок раздела">' +
        '<button type="button" class="ge-del" data-act="del-level">удалить</button>' +
        "</li>";
    }).join("");
    var levelsList = state.levels.length
      ? '<ul class="ge-levels-list">' + levelsItems + "</ul>"
      : '<div class="ge-empty">Уровней пока нет. Добавьте хотя бы один — это разделы переключателя на витрине.</div>';

    var sections = state.levels.slice().sort(byOrder).map(function (l) {
      return levelSection(l.id, l.name);
    }).join("");
    sections += levelSection(null, "Без уровня");

    root.innerHTML =
      '<div class="ge-savebar"><button type="button" id="ge-save" class="button default"' +
        (dirty ? "" : " disabled") + ">Сохранить изменения</button>" +
        '<span id="ge-dirty" class="ge-dirty">' + (dirty ? "есть несохранённые изменения" : "") + "</span></div>" +

      '<div class="ge-card ge-namebox"><h2>Серия (внутреннее имя)</h2>' +
        '<div class="ge-hint">Видно только в админке. На витрине показываются уровни и подписи вариантов.</div>' +
        '<input type="text" id="ge-name" value="' + esc(state.group.name) + '"></div>' +

      '<div class="ge-card"><h2>Уровни (разделы переключателя)</h2>' +
        '<div class="ge-hint">Публичные названия разделов и их порядок на витрине. Удаление уровня снимает его с товаров.</div>' +
        levelsList +
        '<button type="button" class="button" id="ge-add-level">+ Добавить уровень</button></div>' +

      '<div class="ge-card"><h2>Участники (по разделам)</h2>' +
        '<div class="ge-hint">Товары сгруппированы по уровням в порядке разделов. Внутри раздела сортировка — по полю «Порядок в разделе». Чтобы перенести товар в другой раздел, поменяйте «Уровень».</div>' +
        sections +
        '<div class="ge-addbox"><div class="ge-hint">Добавить товар (ищутся только те, что не состоят ни в одной серии):</div>' +
          '<div class="ge-search"><input type="text" id="ge-search" placeholder="Поиск по названию или артикулу…" autocomplete="off"><div class="ge-results" hidden></div></div>' +
        "</div></div>";

    wire();
  }

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

  // структурное действие: сперва сохранить параметры (если есть правки), затем действие, затем перечитать
  function structural(fn) {
    var pre = dirty ? commit() : Promise.resolve();
    return pre.then(fn).then(loadState).catch(function (e) { status(e.message, false); });
  }

  function wire() {
    document.getElementById("ge-save").addEventListener("click", function () {
      commit().then(function () { status("Сохранено", true); loadState(); })
        .catch(function (e) { status(e.message, false); });
    });

    // имя серии
    var nameInput = document.getElementById("ge-name");
    nameInput.addEventListener("input", function () { state.group.name = nameInput.value; markDirty(); });

    // уровни: имя/порядок
    root.querySelectorAll(".ge-levels-list li").forEach(function (li) {
      var id = parseInt(li.getAttribute("data-id"), 10);
      var lvl = state.levels.filter(function (l) { return l.id === id; })[0];
      li.querySelectorAll("input.ge-lf").forEach(function (inp) {
        inp.addEventListener("input", function () {
          if (!lvl) return;
          if (inp.getAttribute("data-f") === "order") lvl.order = parseInt(inp.value, 10) || 0;
          else lvl.name = inp.value;
          markDirty();
        });
      });
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

    // участники: поля + перемещение по уровням + убрать
    root.querySelectorAll("tbody tr[data-id]").forEach(function (tr) {
      var id = parseInt(tr.getAttribute("data-id"), 10);
      var m = state.members.filter(function (x) { return x.id === id; })[0];
      tr.querySelectorAll("input.ge-m").forEach(function (inp) {
        inp.addEventListener("input", function () {
          if (!m) return;
          if (inp.getAttribute("data-f") === "group_order") m.group_order = parseInt(inp.value, 10) || 0;
          else m.variant_label = inp.value;
          markDirty();
        });
      });
      var sel = tr.querySelector("select.ge-movelvl");
      if (sel) sel.addEventListener("change", function () {
        if (!m) return;
        m.group_level = sel.value ? parseInt(sel.value, 10) : null;
        markDirty();
        render(); // переносим строку в нужный раздел (state уже содержит все правки)
      });
      var rm = tr.querySelector('[data-act="remove"]');
      if (rm) rm.addEventListener("click", function () {
        if (!confirm("Убрать товар из серии?")) return;
        structural(function () { return api("member/", { method: "POST", body: { action: "remove", product_id: id } }); })
          .then(function () { status("Убрано", true); });
      });
    });

    // поиск и добавление
    var search = document.getElementById("ge-search");
    resultsEl = root.querySelector(".ge-results");
    var doSearch = debounce(function () {
      var q = search.value.trim();
      if (q.length < 2) { resultsEl.hidden = true; resultsEl.innerHTML = ""; return; }
      api("search/?q=" + encodeURIComponent(q)).then(function (d) {
        if (!d.results.length) {
          resultsEl.innerHTML = '<button type="button" disabled>Ничего не найдено</button>';
        } else {
          resultsEl.innerHTML = d.results.map(function (r) {
            return '<button type="button" data-id="' + r.id + '">' + esc(r.name) +
              (r.sku ? ' <span class="ge-rsku">' + esc(r.sku) + "</span>" : "") + "</button>";
          }).join("");
        }
        resultsEl.hidden = false;
      }).catch(function (e) { status(e.message, false); });
    }, 300);
    search.addEventListener("input", doSearch);
    resultsEl.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-id]");
      if (!btn) return;
      structural(function () { return api("member/", { method: "POST", body: { action: "add", product_id: parseInt(btn.getAttribute("data-id"), 10) } }); })
        .then(function () { status("Добавлено", true); });
    });
  }

  document.addEventListener("click", function (e) {
    if (resultsEl && !e.target.closest(".ge-search")) resultsEl.hidden = true;
  });
  window.addEventListener("beforeunload", function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ""; }
  });

  function loadState() {
    return api("state/").then(function (d) {
      state = { group: d.group || {}, levels: d.levels || [], members: d.members || [] };
      dirty = false;
      render();
    }).catch(function (e) {
      root.textContent = "Не удалось загрузить редактор: " + e.message;
    });
  }

  loadState();
})();
