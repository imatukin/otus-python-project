# Образ приложения: используется и веб-сервером, и celery-воркером.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install --no-cache-dir poetry

WORKDIR /app

# Зависимости ставим отдельным слоем: пересобираются только при правке pyproject/poetry.lock.
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root

# Пользователь с тем же uid, что и на хосте: файлы в примонтированной папке
# (db.sqlite3, media/) не становятся root-овскими.
# (UID нельзя переопределить из bash — он readonly, поэтому имена свои.)
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "$APP_GID" app 2>/dev/null || true \
    && useradd -u "$APP_UID" -g "$APP_GID" -m app 2>/dev/null || true

COPY --chown=$APP_UID:$APP_GID . .

USER $APP_UID:$APP_GID

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
