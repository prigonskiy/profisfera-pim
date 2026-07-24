/* Поле «Цвет варианта (HEX)» в админке: живой образец цвета + системная пипетка.

   Текстовое поле остаётся источником правды — пустое значение так и остаётся
   пустым (нативный <input type="color"> сам по себе показывал бы чёрный и
   незаметно проставлял #000000 товарам без цвета). */
(function () {
  "use strict";

  function normalize(v) {
    var t = String(v || "").trim().replace(/^#/, "").toUpperCase();
    if (/^[0-9A-F]{3}$/.test(t)) t = t.split("").map(function (c) { return c + c; }).join("");
    return /^[0-9A-F]{6}$/.test(t) ? "#" + t : null;
  }

  function enhance(input) {
    if (input.dataset.colorBound) return;
    input.dataset.colorBound = "1";
    input.setAttribute("placeholder", "#RRGGBB");

    var wrap = document.createElement("span");
    wrap.style.cssText = "display:inline-flex;align-items:center;gap:8px;margin-left:8px";

    var swatch = document.createElement("span");
    swatch.style.cssText =
      "width:22px;height:22px;border-radius:4px;border:1px solid #b0b0b0;" +
      "display:inline-block;background:transparent";

    var picker = document.createElement("input");
    picker.type = "color";
    picker.title = "Выбрать цвет";
    picker.style.cssText = "width:28px;height:24px;padding:0;border:0;background:none;cursor:pointer";

    var clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "Очистить";
    clear.style.cssText = "font-size:11px;padding:2px 6px;cursor:pointer";

    wrap.appendChild(swatch);
    wrap.appendChild(picker);
    wrap.appendChild(clear);
    input.parentNode.insertBefore(wrap, input.nextSibling);

    function render() {
      var hex = normalize(input.value);
      if (hex) {
        swatch.style.background = hex;
        swatch.title = hex;
        picker.value = hex;
      } else {
        swatch.style.background = "transparent";
        swatch.title = input.value ? "Не похоже на #RRGGBB" : "Цвет не задан";
      }
    }

    input.addEventListener("input", render);
    input.addEventListener("change", function () {
      var hex = normalize(input.value);
      if (hex) input.value = hex;   // приводим к каноническому виду
      render();
    });
    picker.addEventListener("input", function () {
      input.value = picker.value.toUpperCase();
      render();
    });
    clear.addEventListener("click", function () {
      input.value = "";
      render();
    });

    render();
  }

  function init() {
    document.querySelectorAll("input.pim-hex-color, #id_variant_color").forEach(enhance);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
