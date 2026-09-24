"""Мягкое удаление: вместо DELETE запись помечается удалённой и остаётся в базе.

Модель-наследник `SoftDeleteModel` получает поля пометки и два менеджера:
`objects` видит только живые записи (им пользуется сайт), `all_objects` — все
(им пользуется админка, чтобы удалённое можно было найти и восстановить).

Связанные объекты обычным CASCADE не трогаются — физического удаления нет.
Что делать со связями, модель описывает сама:

- `soft_delete_cascade` — обратные связи, чьи живые записи помечаются удалёнными
  вместе с объектом и восстанавливаются вместе с ним;
- `soft_delete_protect` — обратные связи, при живых записях в которых удалять
  объект нельзя (аналог `on_delete=PROTECT`).
"""

from django.conf import settings
from django.db import models
from django.db.models import ProtectedError
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """Выборка, у которой `delete()` не удаляет, а помечает записи."""

    def delete(self, user=None):
        """Помечает удалёнными все записи выборки (с каскадом, как у модели)."""
        # Идём по объектам, а не делаем один update(): так у каждого срабатывают
        # каскад и защита связей, описанные в модели.
        count = 0
        for obj in self:
            obj.delete(user=user)
            count += 1
        return count, {self.model._meta.label: count}

    delete.alters_data = True
    delete.queryset_only = True

    def restore(self):
        """Снимает пометку «удалено» со всех записей выборки."""
        count = 0
        for obj in self:
            obj.restore()
            count += 1
        return count

    restore.alters_data = True


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Менеджер сайта: удалённые записи не видны."""

    def get_queryset(self):
        """Только записи без пометки «удалено»."""
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    """Абстрактная модель с мягким удалением."""

    is_deleted = models.BooleanField('Удалено', default=False)
    deleted_at = models.DateTimeField('Когда удалено', blank=True, null=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Кто удалил',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        # Обратная связь «что удалил этот пользователь» никому не нужна.
        related_name='+',
    )

    # Порядок важен: первый объявленный менеджер становится менеджером по умолчанию,
    # и именно его используют ModelForm, аутентификация и обратные связи.
    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    soft_delete_cascade = ()
    soft_delete_protect = ()

    class Meta:
        abstract = True

    def _related_manager(self, relation, alive_only=True):
        """Выборка по обратной связи `relation` — только живые или все записи."""
        field = self._meta.get_field(relation)
        model = field.related_model
        manager = model.objects if alive_only else model.all_objects
        return manager.filter(**{field.field.name: self})

    def deleted_related(self):
        """Что пометится удалённым вместе с объектом: {verbose_name_plural: queryset}."""
        result = {}
        for relation in self.soft_delete_cascade:
            queryset = self._related_manager(relation)
            result[queryset.model._meta.verbose_name_plural] = queryset
        return result

    def protected_related(self):
        """Живые связанные записи, которые не дают удалить объект."""
        return [
            obj
            for relation in self.soft_delete_protect
            for obj in self._related_manager(relation)
        ]

    def delete(self, using=None, keep_parents=False, user=None):  # pylint: disable=unused-argument
        """Помечает объект удалённым вместо физического удаления.

        `keep_parents` оставлен ради совместимости с сигнатурой Django: наследование
        с несколькими таблицами у нас не используется, так что он ни на что не влияет.
        """
        protected = self.protected_related()
        if protected:
            raise ProtectedError(
                f'Нельзя удалить «{self}»: на него ссылаются неудалённые записи.',
                set(protected),
            )

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(using=using, update_fields=('is_deleted', 'deleted_at', 'deleted_by'))

        count = 1
        for relation in self.soft_delete_cascade:
            # Детям ставим то же время: по нему restore() узнает, кого вернуть.
            count += self._related_manager(relation).update(
                is_deleted=True, deleted_at=self.deleted_at, deleted_by=user,
            )
        return count, {self._meta.label: 1}

    delete.alters_data = True

    def restore(self):
        """Снимает пометку «удалено» — и с тех, кто был удалён вместе с объектом.

        Записи, удалённые раньше и отдельно (со своим временем удаления), не трогаем.
        """
        if not self.is_deleted:
            return
        for relation in self.soft_delete_cascade:
            self._related_manager(relation, alive_only=False).filter(
                is_deleted=True, deleted_at=self.deleted_at,
            ).update(is_deleted=False, deleted_at=None, deleted_by=None)

        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=('is_deleted', 'deleted_at', 'deleted_by'))

    restore.alters_data = True
