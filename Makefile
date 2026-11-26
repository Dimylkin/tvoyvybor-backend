.PHONY: help install dev-start dev-migrate lint format-check test unit integration integration-postgres migration-check migrate-head seed-stage3 seed-stage6 seed-quests seed-minigames

PYTHON ?= .venv/bin/python
UV ?= uv

define run_with_env
	@test -f .env || { echo 'Создайте и настройте .env по образцу .env.example' >&2; exit 1; }
	@test -x $(PYTHON) || { echo 'Создайте .venv и установите зависимости: make install' >&2; exit 1; }
	@set -a; . ./.env; set +a; \
	for value in "$$DATABASE_URL" "$$JWT_SECRET" "$$CORS_ORIGINS" "$$APP_ENV"; do \
	  test -n "$$value" || { echo 'Заполните DATABASE_URL, JWT_SECRET, CORS_ORIGINS и APP_ENV в .env' >&2; exit 1; }; \
	done; \
	exec $(PYTHON) -m $(1)
endef

help: ## Показать основные цели
	@awk 'BEGIN {FS = ":.*##"}; /^[a-zA-Z_-]+:.*##/ {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Создать окружение и синхронизировать зависимости по uv.lock
	$(UV) sync --locked --extra dev

dev-start: ## Запустить API локально (нужны .env и доступная БД)
	$(call run_with_env,uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)

dev-migrate: ## Применить миграции к DATABASE_URL из .env
	$(call run_with_env,alembic upgrade head)

lint: ## Проверить lint правила Ruff
	$(PYTHON) -m ruff check .

format-check: ## Проверить форматирование Ruff
	$(PYTHON) -m ruff format --check .

test: ## Запустить весь локальный набор тестов
	$(PYTHON) -m pytest -q

unit: ## Запустить unit-тесты без API/БД фикстур
	$(PYTHON) -m pytest -q tests/test_attempt_service.py tests/test_task_strategy.py

integration: ## Запустить API/SQLite, seed и PostgreSQL integration tests (PG test пропускается без TEST_POSTGRES_URL)
	$(PYTHON) -m pytest -q tests/test_auth.py tests/test_content.py tests/test_attempt_api.py tests/test_quest_api.py tests/test_quest_acceptance.py tests/test_minigames.py tests/test_activity_reflection.py tests/test_questionnaire.py tests/test_questionnaire_v2_catalog.py tests/test_questionnaire_v3.py tests/test_career_profile_rules.py tests/test_seed_stage6.py tests/test_health.py tests/test_postgres_serialization.py

integration-postgres: ## Запустить интеграционный тест PostgreSQL (нужен TEST_POSTGRES_URL)
	$(PYTHON) -m pytest -q tests/test_postgres_serialization.py

migration-check: ## Проверить, что граф Alembic заканчивается единственной ожидаемой head
	$(PYTHON) scripts/check_migration_graph.py

migrate-head: ## Применить Alembic миграции к DATABASE_URL из окружения
	$(PYTHON) -m alembic upgrade head

seed-stage3: ## Идемпотентно создать демонстрационные задания этапа 3
	$(call run_with_env,scripts.seed_stage3)

seed-stage6: ## Идемпотентно создать контент этапа 6
	$(call run_with_env,scripts.seed_stage6)

seed-quests: ## Идемпотентно создать демонстрационные квесты
	$(call run_with_env,scripts.seed_quests)

seed-minigames: ## Идемпотентно установить каталог мини-игр
	$(call run_with_env,scripts.seed_minigames)
