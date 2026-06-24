// Динамика инлайна «Фильтры витрины» в админке категории.
// У каждого варианта характеристики проставлен data-ftype (тип характеристики).
// По нему оставляем в списке «Вид фильтра» только подходящие виды.
(function () {
  "use strict";

  // тип характеристики -> допустимые виды отображения (коды CategoryFilter.Display)
  var ALLOWED = {
    boolean: ["bool_checkbox", "bool_yesno"],
    number: ["number_range", "number_buckets"],
    single_select: ["select_checkbox"],
    multi_select: ["select_checkbox"]
  };

  function syncRow(row) {
    if (!row) return;
    var charSel = row.querySelector('select[name$="-characteristic"]');
    var dispSel = row.querySelector('select[name$="-display"]');
    if (!charSel || !dispSel) return;

    var opt = charSel.options[charSel.selectedIndex];
    var ftype = opt ? opt.getAttribute("data-ftype") : null;
    var allowed = ftype ? ALLOWED[ftype] : null; // null => характеристика не выбрана: показываем все

    var selectedStillValid = false;
    Array.prototype.forEach.call(dispSel.options, function (o) {
      if (!o.value) return; // пустой вариант «---------» оставляем всегда
      var ok = !allowed || allowed.indexOf(o.value) !== -1;
      o.hidden = !ok;
      o.disabled = !ok;
      if (ok && o.value === dispSel.value) selectedStillValid = true;
    });

    // если текущий выбранный вид стал недопустимым — переключаем на первый подходящий
    if (allowed && !selectedStillValid) {
      var first = Array.prototype.find.call(dispSel.options, function (o) {
        return o.value && allowed.indexOf(o.value) !== -1;
      });
      dispSel.value = first ? first.value : "";
    }
  }

  function syncAll() {
    document.querySelectorAll('select[name$="-characteristic"]').forEach(function (sel) {
      syncRow(sel.closest("tr") || sel.closest(".form-row") || sel.parentNode);
    });
  }

  // смена характеристики -> пересобрать список видов в этой строке
  document.addEventListener("change", function (e) {
    if (e.target && e.target.matches && e.target.matches('select[name$="-characteristic"]')) {
      syncRow(e.target.closest("tr") || e.target.closest(".form-row") || e.target.parentNode);
    }
  });

  // первичная отрисовка и добавление новой строки инлайна
  document.addEventListener("DOMContentLoaded", syncAll);
  document.addEventListener("formset:added", function () { syncAll(); });
})();
