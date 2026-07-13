# Industrial Knowledge Brain — convenience commands
#
# First time setup:
#   cp .env.example .env   # then edit .env and set GEMINI_API_KEY
#   make up

.PHONY: up down restart logs ps rebuild clean seed health

up: ## Start everything (backend, frontend, bundled Neo4j)
	docker compose up --build

up-d: ## Start everything in the background
	docker compose up --build -d

down: ## Stop and remove containers (keeps data volumes)
	docker compose down

restart: ## Restart all services
	docker compose restart

logs: ## Tail logs from every service
	docker compose logs -f

ps: ## Show running services
	docker compose ps

rebuild: ## Force a clean rebuild of all images
	docker compose build --no-cache

clean: ## Stop containers AND wipe volumes (Neo4j data + Chroma persistence)
	docker compose down -v

health: ## Curl the backend health endpoint
	curl -s http://localhost:8000/health | python3 -m json.tool

seed: ## Ingest the bundled sample documents (requires backend running)
	@for f in backend/data/sample_documents/*.pdf; do \
		echo "Ingesting $$f"; \
		curl -s -X POST http://localhost:8000/api/ingest -F "file=@$$f" | python3 -m json.tool; \
	done

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-10s %s\n", $$1, $$2}'
