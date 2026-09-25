"""Журнал событий по книгам и авторам: кто, что и когда сделал, какие поля изменились.

В журнал попадают только `Book` и `Author` — создание, изменение, удаление и
восстановление. Сайт и админка вызывают `log_created()` / `log_updated()` / ... явно:
кто совершил действие, известно только там, модель о пользователе не знает.

Запись в БД делает фоновая задача `tasks.log_event_task`. Ставится она после фиксации
транзакции: откат не должен оставить в журнале события, которого не было.
Время события фиксируется здесь же, а не в воркере, — очередь может и подождать.
"""

import datetime

from django.db import transaction
from django.utils import timezone

from .models import Author, Book, EventLog
from .soft_delete import SoftDeleteModel
from .tasks import log_event_task

OBJECT_TYPES = {
    Book: EventLog.ObjectType.BOOK,
    Author: EventLog.ObjectType.AUTHOR,
}

# Служебные поля в журнал не пишем: удаление и восстановление — отдельные события.
SKIPPED_FIELDS = {'id', *(field.name for field in SoftDeleteModel._meta.fields)}

# Такие значения у нового объекта означают «не заполнено» — в журнал создания не идут.
EMPTY_VALUES = (None, '', [], False)


def _value(obj, field):
    """Значение поля в виде, пригодном для JSON: связи — строкой, даты — в ISO."""
    if field.many_to_many:
        return sorted(str(item) for item in getattr(obj, field.name).all())
    value = getattr(obj, field.name)
    if field.is_relation:
        return None if value is None else str(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def snapshot(obj):
    """Значения полей объекта: {имя поля: значение}. M2M берутся из базы — объект уже сохранён."""
    fields = (*obj._meta.concrete_fields, *obj._meta.many_to_many)
    return {field.name: _value(obj, field) for field in fields if field.name not in SKIPPED_FIELDS}


def stored_snapshot(obj):
    """Снимок объекта таким, каким он лежит в базе, — вызывать до сохранения формы.

    Сам `obj` для этого не годится: валидация ModelForm уже переписала его поля.
    """
    return snapshot(type(obj).all_objects.get(pk=obj.pk))


def diff(old, new):
    """Изменившиеся поля: {имя: {"old": было, "new": стало}}."""
    return {
        name: {'old': old.get(name), 'new': value}
        for name, value in new.items()
        if old.get(name) != value
    }


def log_event(obj, action, user=None, changes=None):
    """Ставит в очередь запись события о книге или авторе."""
    event = {
        'object_type': OBJECT_TYPES[type(obj)],
        'object_id': obj.pk,
        'object_repr': str(obj)[:EventLog._meta.get_field('object_repr').max_length],
        'action': action,
        'user_id': user.pk if user is not None else None,
        'changes': changes or {},
        'created_at': timezone.now().isoformat(),
    }
    transaction.on_commit(lambda: log_event_task.delay(event))


def log_created(obj, user):
    """Объект создан: в журнал — все заполненные поля как новые значения."""
    changes = {
        name: {'old': None, 'new': value}
        for name, value in snapshot(obj).items()
        if value not in EMPTY_VALUES
    }
    log_event(obj, EventLog.Action.CREATED, user, changes)


def log_updated(obj, user, old):
    """Объект изменён: `old` — снимок до сохранения. Сохранили без изменений — события нет."""
    changes = diff(old, snapshot(obj))
    if changes:
        log_event(obj, EventLog.Action.UPDATED, user, changes)
    return changes


def log_deleted(obj, user):
    """Объект помечен удалённым."""
    log_event(obj, EventLog.Action.DELETED, user)


def log_restored(obj, user):
    """С объекта снята пометка «удалено»."""
    log_event(obj, EventLog.Action.RESTORED, user)
