/* Редактор группировки вариантов — одно окно, без перезагрузок.
 * Общается с JSON-эндпоинтами admin (…/<pk>/editor/…). Без зависимостей. */
(function () {
  "use strict";
  var root = document.getElementById("group-editor");
  if (!root) return;

  var BASE = root.getAttribute("data-base") || location.pathname;
  if (BASE.slice(-1) !== "/") BASE += "/";

  var tokenInput = document.querySelector("[name=csrfmiddlewaretoken]");
  var CSRF = tokenInput ? tokenInput.value : "";

  // --- статус (всплывашка) ---
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
      t = setTimeout(function () { fn.apply(self, a); }, ms || 500);
    };
  }

  var state = { group: {}, levels: [], members: [] };
  var resultsEl = null;

  function levelOptions(selected) {
    var opts = '<option value="">— без уровня —</option>';
    state.levels.forEach(function (l) {
      opts += '<option value="' + l.id + '"' + (l.id === selected ? " selected" : "") +
        ">" + esc(l.name) + "</option>";
    });
    return opts;
  }

  function saveMember(body) {
    api("member/", { method: "POST", body: body })
      .then(function () { status("Сохранено", true); })
      .catch(function (e) { status(e.message, false); });
  }
  function updateLevelOptionText(id, name) {
    root.querySelectorAll('select.ge-f option[value="' + id + '"]').forEach(function (o) {
      o.textContent = name;
    });
  }

  function render() {
    var membersRows = state.members.map(function (m) {
      return '<tr data-id="' + m.id + '">' +
        '<td><div class="ge-pname">' + esc(m.name) + "</div>" +
          (m.sku ? '<div class="ge-psku">Артикул: ' + esc(m.sku) + "</div>" : "") + "</td>" +
        '<td><input type="text" class="ge-f" data-f="variant_label" value="' + esc(m.variant_label) +
          '" placeholder="подпись на кнопке"></td>' +
        '<td class="ge-lvl"><select class="ge-f" data-f="group_level">' + levelOptions(m.group_level) + "</select></td>" +
        '<td class="ge-num"><input type="number" min="0" class="ge-f" data-f="group_order" value="' + (m.group_order || 0) + '"></td>' +
        '<td><button type="button" class="ge-del" data-act="remove">убрать</button></td>' +
        "</tr>";
    }).join("");
    var membersTable = state.members.length
      ? '<table class="ge-table"><thead><tr><th>Товар</th><th>Подпись варианта</th><th>Уровень</th><th>Порядок</th><th></th></tr></thead><tbody>' + membersRows + "</tbody></table>"
      : '<div class="ge-empty">Пока нет участников. Найдите и добавьте товары ниже.</div>';

    var levelsItems = state.levels.map(function (l) {
      return '<li data-id="' + l.id + '">' +
        '<input type="text" class="ge-lf ge-lname" data-f="name" value="' + esc(l.name) + '">' +
        '<input type="number" min="0" class="ge-lf ge-lorder" data-f="order" value="' + (l.order || 0) + '" title="Порядок">' +
        '<button type="button" class="ge-del" data-act="del-level">удалить</button>' +
        "</li>";
    }).join("");
    var levelsList = state.levels.length
      ? '<ul class="ge-levels-list">' + levelsItems + "</ul>"
      : '<div class="ge-empty">Уровней пока нет. Добавьте хотя бы один — это разделы переключателя на витрине.</div>';

    root.innerHTML =
      '<div class="ge-card ge-namebox"><h2>Серия (внутреннее имя)</h2>' +
        '<div class="ge-hint">Видно только в админке. На витрине показываются уровни и подписи вариантов.</div>' +
        '<input type="text" id="ge-name" value="' + esc(state.group.name) + '"></div>' +
      '<div class="ge-card"><h2>Уровни</h2>' +
        '<div class="ge-hint">Публичные названия разделов переключателя (напр. «Наборы», «Отдельные шприцы»). Удаление уровня снимает его с товаров.</div>' +
        levelsList +
        '<button type="button" class="button" id="ge-add-level">+ Добавить уровень</button></div>' +
      '<div class="ge-card"><h2>Участники</h2>' +
        '<div class="ge-hint">Товары этой серии. Подпись — текст на кнопке варианта; уровень — раздел; порядок — сортировка внутри уровня.</div>' +
        membersTable +
        '<div style="margin-top:14px"><div class="ge-hint">Добавить товар (ищутся только те, что не состоят ни в одной серии):</div>' +
          '<div class="ge-search"><input type="text" id="ge-search" placeholder="Поиск по названию или артикулу…" autocomplete="off"><div class="ge-results" hidden></div></div>' +
        "</div></div>";

    wire();
  }

  function wire() {
    // имя серии
    var nameInput = document.getElementById("ge-name");
    nameInput.addEventListener("input", debounce(function () {
      api("rename/", { method: "POST", body: { name: nameInput.value } })
        .then(function () { status("Сохранено", true); })
        .catch(function (e) { status(e.message, false); });
    }, 500));

    // участники
    root.querySelectorAll("tbody tr").forEach(function (tr) {
      var id = parseInt(tr.getAttribute("data-id"), 10);
      tr.querySelectorAll("input.ge-f").forEach(function (inp) {
        inp.addEventListener("input", debounce(function () {
          var body = { action: "update", product_id: id };
          body[inp.getAttribute("data-f")] = inp.value;
          saveMember(body);
        }, 500));
      });
      var sel = tr.querySelector("select.ge-f");
      if (sel) sel.addEventListener("change", function () {
        saveMember({ action: "update", product_id: id, group_level: sel.value || null });
      });
      var rm = tr.querySelector('[data-act="remove"]');
      if (rm) rm.addEventListener("click", function () {
        if (!confirm("Убрать товар из серии?")) return;
        api("member/", { method: "POST", body: { action: "remove", product_id: id } })
          .then(function () { status("Убрано", true); loadState(); })
          .catch(function (e) { status(e.message, false); });
      });
    });

    // уровни
    root.querySelectorAll(".ge-levels-list li").forEach(function (li) {
      var id = parseInt(li.getAttribute("data-id"), 10);
      li.querySelectorAll("input.ge-lf").forEach(function (inp) {
        inp.addEventListener("input", debounce(function () {
          var body = { action: "update", level_id: id };
          body[inp.getAttribute("data-f")] = inp.value;
          api("level/", { method: "POST", body: body })
            .then(function (d) {
              status("Сохранено", true);
              if (inp.getAttribute("data-f") === "name" && d.level) updateLevelOptionText(id, d.level.name);
            })
            .catch(function (e) { status(e.message, false); });
        }, 500));
      });
      var del = li.querySelector('[data-act="del-level"]');
      if (del) del.addEventListener("click", function () {
        if (!confirm("Удалить уровень? Товары этого уровня останутся без уровня.")) return;
        api("level/", { method: "POST", body: { action: "delete", level_id: id } })
          .then(function () { status("Удалено", true); loadState(); })
          .catch(function (e) { status(e.message, false); });
      });
    });
    document.getElementById("ge-add-level").addEventListener("click", function () {
      api("level/", { method: "POST", body: { action: "add", name: "Новый уровень" } })
        .then(function () { status("Уровень добавлен", true); loadState(); })
        .catch(function (e) { status(e.message, false); });
    });

    // поиск и добавление
    var search = document.getElementById("ge-search");
    resultsEl = root.querySelector(".ge-results");
    var doSearch = debounce(function () {
      var q = search.value.trim();
      if (q.length < 2) { resultsEl.hidden = true; resultsEl.innerHTML = ""; return; }
      api("search/?q=" + encodeURIComponent(q)).then(function (d) {
        if (!d.results.length) {
          resultsEl.innerHTML = "<button type=\"button\" disabled>Ничего не найдено</button>";
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
      api("member/", { method: "POST", body: { action: "add", product_id: parseInt(btn.getAttribute("data-id"), 10) } })
        .then(function () { status("Добавлено", true); loadState(); })
        .catch(function (e2) { status(e2.message, false); });
    });
  }

  // закрытие выпадашки поиска по клику вне — один слушатель на весь редактор
  document.addEventListener("click", function (e) {
    if (resultsEl && !e.target.closest(".ge-search")) resultsEl.hidden = true;
  });

  function loadState() {
    api("state/").then(function (d) {
      state = { group: d.group || {}, levels: d.levels || [], members: d.members || [] };
      render();
    }).catch(function (e) {
      root.textContent = "Не удалось загрузить редактор: " + e.message;
    });
  }

  loadState();
})();
