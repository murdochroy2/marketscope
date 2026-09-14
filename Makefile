.PHONY: setup db migrate api web dev test test-backend test-frontend lint demo up down

setup:            ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && npm install

db:               ## Start Postgres in Docker
	docker compose up -d --wait db

migrate: db       ## Create tables and seed reference data
	cd backend && uv run alembic upgrade head

api:              ## Run the API on :8000 with live providers (Overpass + Nominatim)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

demo:             ## Run the API offline, with captured OpenStreetMap data
	cd backend && PLACES_PROVIDER=fixture GEOCODER=fixture uv run uvicorn app.main:app --reload --port 8000

web:              ## Run the frontend on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test: test-backend test-frontend  ## Run every test suite

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npx vitest run

lint:
	cd backend && uv run ruff check app tests migrations && uv run ruff format --check app tests migrations
	cd frontend && npx tsc -b && npx oxlint src

up:               ## Build and run the whole stack in Docker on :8080
	docker compose up --build

down:
	docker compose down
