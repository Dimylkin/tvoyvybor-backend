.PHONY: dev-start dev-migrate

define run_with_env
	@test -f .env || { echo 'Создайте и настройте .env по образцу .env.example' >&2; exit 1; }
	@test -x .venv/bin/python || { echo 'Создайте .venv и установите зависимости: pip install -e ".[dev]"' >&2; exit 1; }
	@set -a; . ./.env; set +a; \
	for value in "$$DATABASE_URL" "$$JWT_SECRET" "$$CORS_ORIGINS" "$$APP_ENV"; do \
	  test -n "$$value" || { echo 'Заполните DATABASE_URL, JWT_SECRET, CORS_ORIGINS и APP_ENV в .env' >&2; exit 1; }; \
	done; \
	exec .venv/bin/python -m $(1)
endef

dev-start:
	$(call run_with_env,uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)

dev-migrate:
	$(call run_with_env,alembic upgrade head)
