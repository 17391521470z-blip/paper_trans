SHELL := /bin/bash
.PHONY: install dev test test-backend test-frontend test-e2e lint typecheck build deploy

BACKEND_DIR := backend
FRONTEND_DIR := frontend

install:
	pip install -r $(BACKEND_DIR)/requirements.txt
	npm --prefix $(FRONTEND_DIR) ci

dev:
	docker compose up -d

test: test-backend test-frontend test-e2e

test-backend:
	cd $(BACKEND_DIR) && python -m pytest tests/ -v --tb=short --no-header -x

test-frontend:
	npm --prefix $(FRONTEND_DIR) run typecheck
	npm --prefix $(FRONTEND_DIR) run lint

test-e2e:
	npx playwright test --project=chromium

lint:
	ruff check $(BACKEND_DIR)/
	npm --prefix $(FRONTEND_DIR) run lint

typecheck:
	mypy $(BACKEND_DIR)/
	npm --prefix $(FRONTEND_DIR) run typecheck

build:
	docker compose build

deploy:
	ssh deploy.sh
