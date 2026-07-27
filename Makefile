PYTHON ?= python3
NPM ?= npm

.PHONY: api-install api-lock api-dev web-install web-dev migrate test lint format typecheck build sample reset backup restore provider-health docker-up docker-down

api-install:
	cd apps/api && $(PYTHON) -m pip install -e '.[dev]'

api-lock:
	cd apps/api && $(PYTHON) -m piptools compile pyproject.toml --output-file requirements.lock --generate-hashes --strip-extras --resolver=backtracking

api-dev:
	cd apps/api && $(PYTHON) -m uvicorn app.main:app --reload --port 8000

web-install:
	cd apps/web && $(NPM) ci

web-dev:
	cd apps/web && $(NPM) run dev

migrate:
	cd apps/api && $(PYTHON) -m alembic upgrade head

test:
	cd apps/api && $(PYTHON) -m pytest
	cd apps/web && $(NPM) test

lint:
	cd apps/api && $(PYTHON) -m ruff check .
	cd apps/web && $(NPM) run lint

format:
	cd apps/api && $(PYTHON) -m ruff format .
	cd apps/web && $(NPM) run format

typecheck:
	cd apps/api && $(PYTHON) -m mypy app
	cd apps/web && $(NPM) exec -- tsc -b

build:
	cd apps/web && $(NPM) run build

sample:
	cd apps/api && $(PYTHON) ../../scripts/load_sample.py

reset:
	$(PYTHON) scripts/reset_local_data.py

backup:
	cd apps/api && $(PYTHON) ../../scripts/backup_data.py $(if $(BACKUP_PATH),--output "$(abspath $(BACKUP_PATH))",)

restore:
	@test -n "$(RESTORE_PATH)" || (echo "Set RESTORE_PATH to a .ctbackup archive" && exit 2)
	cd apps/api && $(PYTHON) ../../scripts/restore_backup.py "$(abspath $(RESTORE_PATH))" --confirm REPLACE

provider-health:
	$(PYTHON) scripts/provider_health.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
