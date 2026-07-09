/* Реактивная форма модуля курса в админке.
   По выбранному типу показываем только нужные поля:
     видео    → «Ссылка на видео (embed)»
     слайды   → «Пакет (zip)»
     лонгрид  → «Пакет (zip)»
   Остальные поля модуля скрываем. Работает и в инлайне (таблица) под курсом,
   и в отдельной форме модуля, и на строках, добавленных «+ Добавить ещё один».
*/
(function () {
  "use strict";

  var MAP = {
    video:    { show: ["video_url"], hide: ["package", "body"] },
    slides:   { show: ["package"],   hide: ["video_url", "body"] },
    longread: { show: ["package"],   hide: ["video_url", "body"] },
    "":       { show: [],            hide: ["video_url", "package", "body"] }
  };

  function scopeOf(select) {
    // в табличном инлайне область — строка <tr>; в обычной форме — вся форма
    return select.closest("tr") || select.closest("form") || document;
  }

  function setVisible(el, visible) {
    if (!el) return;
    if (el.tagName === "TD") {
      // не ломаем выравнивание таблицы: прячем содержимое ячейки, а не ячейку
      Array.prototype.forEach.call(el.children, function (child) {
        child.style.display = visible ? "" : "none";
      });
    } else {
      el.style.display = visible ? "" : "none";
    }
  }

  function apply(select) {
    var conf = MAP[select.value] || MAP[""];
    var scope = scopeOf(select);
    conf.hide.forEach(function (name) {
      scope.querySelectorAll(".field-" + name).forEach(function (el) { setVisible(el, false); });
    });
    conf.show.forEach(function (name) {
      scope.querySelectorAll(".field-" + name).forEach(function (el) { setVisible(el, true); });
    });
  }

  function bind(select) {
    if (select.dataset.kindBound) return;
    select.dataset.kindBound = "1";
    select.addEventListener("change", function () { apply(select); });
    apply(select);
  }

  function bindAll(root) {
    (root || document)
      .querySelectorAll('select[name$="-kind"], select[name="kind"], #id_kind')
      .forEach(bind);
  }

  document.addEventListener("DOMContentLoaded", function () { bindAll(document); });
  // Django шлёт это событие при добавлении новой строки инлайна
  document.addEventListener("formset:added", function (e) { bindAll(e.target || document); });
})();
