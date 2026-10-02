COMPOSE ?= docker compose
RUN := $(COMPOSE) run --rm app

.PHONY: up down build logs migrate load shell test lint format lock

.env:
	cp .env.example .env

up: .env
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f app

migrate:
	$(RUN) python manage.py migrate

load:
	$(RUN) sh -c "python manage.py import_places && python manage.py import_stations"

shell:
	$(RUN) python manage.py shell

test:
	$(RUN) pytest

lint:
	$(RUN) sh -c "ruff check . && ruff format --check ."

format:
	$(RUN) sh -c "ruff format . && ruff check --fix ."

lock:
	docker run --rm -v "$(CURDIR)":/app -w /app ghcr.io/astral-sh/uv:python3.13-bookworm-slim uv lock
