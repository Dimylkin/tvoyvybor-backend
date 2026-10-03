# ТвойВыбор.exe — backend

Основа монолитного API на FastAPI. `GET /health` возвращает `{"status":"ok"}`
после успешного запроса к PostgreSQL или HTTP 503, если база недоступна.
На этапе 1 добавлены пользовательская схема и авторизация.

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

Миграция `0001_stage_0` создаёт историю Alembic, а `0002_users` — таблицу
пользователей этапа 1. Compose применяет обе миграции перед запуском API.

## Аутентификация этапа 1

API принимает JSON. `POST /auth/register` с `{"email":"user@example.com",
"password":"password123"}` возвращает HTTP 201 и `id`, нормализованный
`email`, `role: "user"`. Пароль: 8–128 символов; дополнительные поля (в том
числе `role`) отклоняются. Повторный email возвращает 409.

`POST /auth/login` принимает те же поля и возвращает HTTP 200 с
`access_token` и `token_type: "bearer"`. Неверные учётные данные дают 401.
`GET /auth/me` требует заголовок `Authorization: Bearer <access_token>` и
возвращает `id`, `email`, `role`; отсутствие или недействительность токена дают
401. Access JWT подписывается HS256 секретом `JWT_SECRET` и действует 1 час.
Refresh token на этом этапе не нужен. Пароли хранятся в виде PBKDF2-SHA256
с индивидуальной солью; публичная регистрация всегда присваивает роль `user`.
Роль `admin` проверяется на сервере по текущей записи пользователя в БД.
Выдача роли администратору через пользовательский API не предусмотрена на
этом этапе; отдельный порядок назначения нужен перед внедрением admin UI.

В ТЗ не зафиксированы точные поля и статусы auth API; этот минимальный контракт
принят для этапа 1. Интерфейс авторизации React появится на этапе 4 roadmap.
