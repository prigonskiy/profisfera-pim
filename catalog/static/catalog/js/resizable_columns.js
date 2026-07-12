/* Изменение ширины колонок списка мышью (перетаскиванием границы заголовка).
   Ширины запоминаются в браузере (localStorage) отдельно для каждой страницы
   списка. Двойной клик по границе — сброс ширины колонки. */
(function () {
  "use strict";
  var KEY = "pim_col_widths::" + location.pathname;

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

  function init() {
    var table = document.getElementById("result_list");
    if (!table) return;
    table.style.tableLayout = "fixed";  // явные ширины становятся главными

    var ths = table.querySelectorAll("thead th");
    var widths = load();

    ths.forEach(function (th, i) {
      if (widths[i]) setW(th, widths[i]);
      th.style.position = "relative";

      var grip = document.createElement("span");
      grip.style.cssText =
        "position:absolute;top:0;right:0;width:7px;height:100%;" +
        "cursor:col-resize;user-select:none;z-index:5";
      th.appendChild(grip);

      var startX, startW;
      function onMove(ev) {
        var w = Math.max(40, startW + (ev.pageX - startX));
        setW(th, w);
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.userSelect = "";
        widths[i] = th.offsetWidth;
        save(widths);
      }
      grip.addEventListener("mousedown", function (e) {
        startX = e.pageX;
        startW = th.offsetWidth;
        document.body.style.userSelect = "none";
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
        e.preventDefault();
        e.stopPropagation();  // не запускать сортировку по клику на границе
      });
      // клик по гриппу не должен сортировать колонку
      grip.addEventListener("click", function (e) { e.stopPropagation(); });
      // двойной клик по границе — сброс ширины этой колонки
      grip.addEventListener("dblclick", function (e) {
        e.stopPropagation();
        th.style.width = th.style.minWidth = th.style.maxWidth = "";
        delete widths[i];
        save(widths);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
