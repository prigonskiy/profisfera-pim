/* Ширина колонок списка меняется мышью (перетаскиванием границы заголовка).
   Ширины запоминаются в браузере (localStorage) отдельно для каждой страницы.
   Двойной клик по границе — сброс ширины колонки.
   Плюс: содержимое ячеек переносится внутри своей ширины (не наезжает на соседей),
   и заданы разумные стартовые ширины. */
(function () {
  "use strict";
  var KEY = "pim_col_widths::" + location.pathname;

  // стартовые ширины по классу колонки (Django ставит th class="column-<поле>")
  var DEFAULTS = {
    "action-checkbox-column": 28,
    "column-image_tag": 62,
    "column-sku": 110,
    "column-name": 190,
    "column-category": 230,
    "column-brand": 120,
    "column-group": 140,
    "column-manufacturer_sku": 130,
    "column-documents_list": 210,
    "column-is_active": 74,
    "column-updated_at": 140
  };

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; }
  }
  function save(w) {
    try { localStorage.setItem(KEY, JSON.stringify(w)); } catch (e) {}
  }
  function setW(th, px) {
    th.style.width = px + "px";
    th.style.minWidth = px + "px";
    th.style.maxWidth = px + "px";
  }
  function defaultFor(th) {
    for (var cls in DEFAULTS) {
      if (th.classList.contains(cls)) return DEFAULTS[cls];
    }
    return null;
  }

  function injectCss() {
    var css =
      "#result_list{table-layout:fixed;width:100%}" +
      "#result_list th,#result_list td{overflow:hidden;vertical-align:top;" +
      "white-space:normal;word-break:break-word;overflow-wrap:anywhere}" +
      "#result_list td .pim-col-grip{display:none}";
    var s = document.createElement("style");
    s.textContent = css;
    document.head.appendChild(s);
  }

  function init() {
    var table = document.getElementById("result_list");
    if (!table) return;
    injectCss();

    var ths = table.querySelectorAll("thead th");
    var widths = load();

    ths.forEach(function (th, i) {
      // приоритет: сохранённая ширина → дефолт по колонке → без явной ширины
      if (widths[i]) setW(th, widths[i]);
      else {
        var d = defaultFor(th);
        if (d) setW(th, d);
      }
      th.style.position = "relative";

      var grip = document.createElement("span");
      grip.className = "pim-col-grip";
      grip.style.cssText =
        "position:absolute;top:0;right:0;width:7px;height:100%;" +
        "cursor:col-resize;user-select:none;z-index:5";
      th.appendChild(grip);

      var startX, startW;
      function onMove(ev) { setW(th, Math.max(40, startW + (ev.pageX - startX))); }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.userSelect = "";
        widths[i] = th.offsetWidth;
        save(widths);
      }
      grip.addEventListener("mousedown", function (e) {
        startX = e.pageX; startW = th.offsetWidth;
        document.body.style.userSelect = "none";
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
        e.preventDefault(); e.stopPropagation();
      });
      grip.addEventListener("click", function (e) { e.stopPropagation(); });
      grip.addEventListener("dblclick", function (e) {
        e.stopPropagation();
        th.style.width = th.style.minWidth = th.style.maxWidth = "";
        delete widths[i]; save(widths);
        var d = defaultFor(th); if (d) setW(th, d);
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
