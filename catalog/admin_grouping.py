"""Группировка моделей на главной странице админки по смыслу.

Django по умолчанию сваливает все модели приложения в один блок. Здесь мы
переопределяем формирование списка на главной (get_app_list), раскладывая модели
catalog на 4 смысловых раздела. Ссылки и права не меняются — только визуальная
группировка. Модели, не попавшие в карту, уходят в «Каталог: прочее» (ничего не
теряется). На страницах отдельного приложения поведение стандартное.
"""
from django.contrib import admin

_orig_get_app_list = admin.site.get_app_list

GROUPS = [
    ("Каталог: товары и характеристики",
     ["Product", "Category", "Characteristic", "Brand", "Audience",
      "Direction", "Document", "ProductGroup", "GroupLevel"]),
    ("Торговые предложения",
     ["Seller", "Warehouse", "Region", "Offer"]),
    ("Обучение",
     ["Course", "CourseModule"]),
    ("Клиенты и юрлица",
     ["Client", "LegalEntity", "ClientToken"]),
]


def grouped_get_app_list(request, app_label=None):
    # на странице отдельного приложения — стандартное поведение
    if app_label:
        return _orig_get_app_list(request, app_label)

    app_dict = admin.site._build_app_dict(request)
    catalog = app_dict.pop("catalog", None)
    result = []

    if catalog:
        by_name = {m["object_name"]: m for m in catalog["models"]}
        assigned = set()
        base = {
            "app_label": "catalog",
            "app_url": catalog["app_url"],
            "has_module_perms": catalog["has_module_perms"],
        }
        for name, objs in GROUPS:
            models = [by_name[o] for o in objs if o in by_name]
            assigned.update(o for o in objs if o in by_name)
            if models:
                result.append(dict(base, name=name, models=models))
        leftover = [m for o, m in by_name.items() if o not in assigned]
        if leftover:
            result.append(dict(base, name="Каталог: прочее", models=leftover))

    # остальные приложения (Пользователи и группы, Токены) — как есть
    for label in sorted(app_dict):
        result.append(app_dict[label])
    return result


admin.site.get_app_list = grouped_get_app_list
