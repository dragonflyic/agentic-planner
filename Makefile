.PHONY: setup dev db-up db-down migrate backend frontend worker test clean

# Colors for output
CYAN := \033[0;36m
NC := \033[0m

# =============================================================================
# SETUP
# =============================================================================

setup: ## Install all dependencies
	@echo "$(CYAN)Installing backend dependencies...$(NC)"
	cd backend && poetry install
	@echo "$(CYAN)Installing frontend dependencies...$(NC)"
	cd frontend && npm install
	@echo "$(CYAN)Setup complete!$(NC)"

# =============================================================================
# DATABASE
# =============================================================================

db-up: ## Start PostgreSQL
	@echo "$(CYAN)Starting PostgreSQL...$(NC)"
	docker-compose up -d postgres
	@echo "$(CYAN)Waiting for PostgreSQL to be ready...$(NC)"
	@sleep 3
	@docker-compose exec -T postgres pg_isready -U workbench || (echo "PostgreSQL not ready" && exit 1)
	@echo "$(CYAN)PostgreSQL is ready!$(NC)"

db-down: ## Stop PostgreSQL
	@echo "$(CYAN)Stopping PostgreSQL...$(NC)"
	docker-compose down

db-reset: db-down ## Reset database (destroys all data)
	@echo "$(CYAN)Removing PostgreSQL data...$(NC)"
	docker volume rm agentic-planner_postgres_data 2>/dev/null || true
	@$(MAKE) db-up
	@$(MAKE) migrate

# =============================================================================
# MIGRATIONS
# =============================================================================

migrate: ## Run database migrations
	@echo "$(CYAN)Running migrations...$(NC)"
	cd backend && poetry run alembic upgrade head

migrate-new: ## Create new migration (usage: make migrate-new msg="description")
	@echo "$(CYAN)Creating new migration...$(NC)"
	cd backend && poetry run alembic revision --autogenerate -m "$(msg)"

# =============================================================================
# DEVELOPMENT
# =============================================================================

dev: db-up ## Start all development servers
	@echo "$(CYAN)Starting development servers...$(NC)"
	@$(MAKE) -j3 backend frontend worker

backend: ## Start FastAPI backend
	@echo "$(CYAN)Starting FastAPI backend on http://localhost:8000$(NC)"
	cd backend && poetry run uvicorn workbench.main:app --reload --host 0.0.0.0 --port 8000

frontend: ## Start Next.js frontend
	@echo "$(CYAN)Starting Next.js frontend on http://localhost:3000$(NC)"
	cd frontend && npm run dev

worker: ## Start background worker
	@echo "$(CYAN)Starting background worker...$(NC)"
	cd backend && poetry run python -m workbench.worker.runner

# =============================================================================
# TESTING
# =============================================================================

test: ## Run all tests
	@echo "$(CYAN)Running backend tests...$(NC)"
	cd backend && poetry run pytest -v
	@echo "$(CYAN)Running frontend tests...$(NC)"
	cd frontend && npm test -- --passWithNoTests

test-backend: ## Run backend tests only
	cd backend && poetry run pytest -v

test-frontend: ## Run frontend tests only
	cd frontend && npm test

# =============================================================================
# LINTING
# =============================================================================

lint: ## Run linters
	@echo "$(CYAN)Linting backend...$(NC)"
	cd backend && poetry run ruff check src/
	@echo "$(CYAN)Linting frontend...$(NC)"
	cd frontend && npm run lint

lint-fix: ## Fix linting issues
	cd backend && poetry run ruff check --fix src/
	cd frontend && npm run lint -- --fix

typecheck: ## Run type checking
	@echo "$(CYAN)Type checking backend...$(NC)"
	cd backend && poetry run mypy src/
	@echo "$(CYAN)Type checking frontend...$(NC)"
	cd frontend && npm run typecheck

# =============================================================================
# UTILITIES
# =============================================================================

clean: ## Clean up generated files
	@echo "$(CYAN)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/.next 2>/dev/null || true

logs: ## Show docker logs
	docker-compose logs -f

shell-db: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U workbench -d workbench

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(CYAN)%-15s$(NC) %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
