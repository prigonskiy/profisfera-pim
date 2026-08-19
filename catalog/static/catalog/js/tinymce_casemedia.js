/* Плагин TinyMCE: вставка изображения из галереи кейса.
   Кнопка «Галерея» открывает модалку с загруженными CaseMedia этого кейса;
   выбор вставляет <figure data-media="ID">…</figure>. data-media — источник
   правды: при отдаче через API src подменяется на актуальный preview-URL. */
tinymce.PluginManager.add("casemedia", function (editor) {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function caseChangePath() {
    // на форме редактирования URL вида /admin/catalog/case/<pk>/change/
    return /\/case\/\d+\/change\/?$/.test(window.location.pathname)
      ? window.location.pathname.replace(/change\/?$/, "") : null;
  }

  function closeModal() {
    var el = document.getElementById("cm-overlay");
    if (el) el.parentNode.removeChild(el);
  }

  function insert(m) {
    var cap = m.caption ? "<figcaption>" + esc(m.caption) + "</figcaption>" : "";
    editor.insertContent(
      '<figure data-media="' + m.id + '">' +
      '<img src="' + esc(m.thumb) + '" alt="' + esc(m.caption) + '">' +
      cap + "</figure><p></p>");
    closeModal();
  }

  function showModal(items) {
    closeModal();
    var overlay = document.createElement("div");
    overlay.id = "cm-overlay";
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.55);" +
      "display:flex;align-items:center;justify-content:center";
    var panel = document.createElement("div");
    panel.style.cssText =
      "background:#fff;color:#222;max-width:760px;max-height:80vh;overflow:auto;" +
      "border-radius:8px;padding:16px;box-shadow:0 10px 40px rgba(0,0,0,.3)";
    var head = "<div style='display:flex;justify-content:space-between;align-items:center;" +
      "margin-bottom:12px'><b>Галерея кейса</b>" +
      "<button type='button' id='cm-close' style='cursor:pointer'>Закрыть</button></div>";

    if (!items.length) {
      panel.innerHTML = head +
        "<p style='color:#666'>В галерее пока нет изображений. Добавьте их в блоке " +
        "«Изображения кейса», сохраните кейс — и они появятся здесь.</p>";
    } else {
      var grid = items.map(function (m) {
        return "<figure data-id='" + m.id + "' class='cm-item' style='cursor:pointer;margin:0;" +
          "border:1px solid #e2e2e2;border-radius:6px;padding:6px;text-align:center'>" +
          "<img src='" + esc(m.thumb) + "' style='width:100%;height:96px;object-fit:contain'>" +
          "<figcaption style='font-size:11px;color:#555;margin-top:4px'>" +
          esc(m.caption || ("#" + m.id)) + "</figcaption></figure>";
      }).join("");
      panel.innerHTML = head +
        "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px'>" + grid + "</div>";
    }
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target.id === "cm-close") { closeModal(); return; }
      var fig = e.target.closest(".cm-item");
      if (fig) {
        var id = +fig.getAttribute("data-id");
        var m = items.filter(function (x) { return x.id === id; })[0];
        if (m) insert(m);
      }
    });
  }

  function openPicker() {
    var base = caseChangePath();
    if (!base) {
      editor.notificationManager.open({
        text: "Сначала сохраните кейс и добавьте изображения в галерею.", type: "info", timeout: 4000 });
      return;
    }
    fetch(base + "media-json/", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { showModal(data.results || []); })
      .catch(function () {
        editor.notificationManager.open({ text: "Не удалось загрузить галерею.", type: "error" }); });
  }

  editor.ui.registry.addButton("casemedia", {
    text: "Галерея",
    tooltip: "Вставить изображение из галереи кейса",
    onAction: openPicker,
  });
});
