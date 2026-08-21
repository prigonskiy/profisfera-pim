/* Плагин TinyMCE: вставка карточки товара в тело кейса.
   Кнопка «Товар» открывает модалку с товарами, привязанными к кейсу (блок
   «Товары кейса»); выбор вставляет маркер <div data-product="SLUG">. Витрина
   превращает маркер в карточку, данные берёт из case.products по slug.
   Чтобы упомянуть товар — сначала привяжите его к кейсу и сохраните. */
tinymce.PluginManager.add("caseproduct", function (editor) {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function caseChangePath() {
    return /\/case\/\d+\/change\/?$/.test(window.location.pathname)
      ? window.location.pathname.replace(/change\/?$/, "") : null;
  }

  function closeModal() {
    var el = document.getElementById("cp-overlay");
    if (el) el.parentNode.removeChild(el);
  }

  function insert(p) {
    // видимый в редакторе чип; при отдаче PIM нормализует его в чистый маркер
    editor.insertContent(
      '<div class="cp-chip" data-product="' + esc(p.slug) + '" contenteditable="false" ' +
      'style="display:inline-block;border:1px solid #b7d3ce;border-radius:6px;' +
      'padding:4px 10px;margin:2px 0;background:#eef7f5;color:#12655b;font-size:13px">' +
      "🛒 " + esc(p.name) + "</div><p></p>");
    closeModal();
  }

  function showModal(items) {
    closeModal();
    var overlay = document.createElement("div");
    overlay.id = "cp-overlay";
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.55);" +
      "display:flex;align-items:center;justify-content:center";
    var panel = document.createElement("div");
    panel.style.cssText =
      "background:#fff;color:#222;max-width:620px;max-height:80vh;overflow:auto;" +
      "border-radius:8px;padding:16px;box-shadow:0 10px 40px rgba(0,0,0,.3)";
    var head = "<div style='display:flex;justify-content:space-between;align-items:center;" +
      "margin-bottom:12px'><b>Товары кейса</b>" +
      "<button type='button' id='cp-close' style='cursor:pointer'>Закрыть</button></div>";

    if (!items.length) {
      panel.innerHTML = head +
        "<p style='color:#666'>К кейсу пока не привязано ни одного товара. Добавьте товары " +
        "в блоке «Товары кейса», сохраните — и они появятся здесь.</p>";
    } else {
      var rows = items.map(function (p) {
        var dim = p.active ? "" : "opacity:.5";
        var tag = p.active ? "" : " <span style='color:#c0392b;font-size:11px'>(неактивен)</span>";
        return "<div class='cp-item' data-slug='" + esc(p.slug) + "' style='display:flex;" +
          "align-items:center;gap:10px;padding:8px;border:1px solid #eee;border-radius:6px;" +
          "margin-bottom:8px;cursor:pointer;" + dim + "'>" +
          "<img src='" + esc(p.thumb) + "' style='width:44px;height:44px;object-fit:contain;" +
          "background:#fff;border:1px solid #f0f0f0;border-radius:4px'>" +
          "<span style='font-size:13px'>" + esc(p.name) + tag + "</span></div>";
      }).join("");
      panel.innerHTML = head + rows;
    }
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target.id === "cp-close") { closeModal(); return; }
      var row = e.target.closest(".cp-item");
      if (row) {
        var slug = row.getAttribute("data-slug");
        var p = items.filter(function (x) { return x.slug === slug; })[0];
        if (p) insert(p);
      }
    });
  }

  function openPicker() {
    var base = caseChangePath();
    if (!base) {
      editor.notificationManager.open({
        text: "Сначала сохраните кейс и привяжите к нему товары.", type: "info", timeout: 4000 });
      return;
    }
    fetch(base + "products-json/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { showModal(data.results || []); })
      .catch(function () {
        editor.notificationManager.open({ text: "Не удалось загрузить товары.", type: "error" }); });
  }

  editor.ui.registry.addButton("caseproduct", {
    text: "Товар",
    tooltip: "Вставить карточку товара из привязанных к кейсу",
    onAction: openPicker,
  });
});
