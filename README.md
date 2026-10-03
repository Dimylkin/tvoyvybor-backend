# ТвойВыбор.exe — backend

Основа монолитного API на FastAPI. На этапе 0 доступен только `GET /health`:
он возвращает `{"status":"ok"}` после успешного запроса к PostgreSQL или
HTTP 503, если база недоступна. Пользовательская схема и авторизация появятся
на этапе 1 roadmap.

## Локальный запуск

Общий Docker Compose находится в соседнем репозитории
`../tvoyvybor-frontend/docker-compose.yml`. Его инструкция запуска описана в
README frontend-репозитория. В backend контейнер передаются `DATABASE_URL`,
`JWT_SECRET`, `CORS_ORIGINS` и `APP_ENV`; образ собирается из этого каталога.

Для отдельного запуска скопируйте `.env.example` в `.env`, укажите действующие
параметры локальной PostgreSQL и выполните:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install '.[dev]'
set -a; . ./.env; set +a
alembic upgrade head
uvicorn app.main:app --reload
```

Проверка: `curl http://localhost:8000/health`.

## Проверки качества

```sh
ruff format --check .
ruff check .
pytest
```

Миграция `0001_stage_0` создаёт только таблицу истории Alembic. Создание
прикладных таблиц относится к этапу 1.
