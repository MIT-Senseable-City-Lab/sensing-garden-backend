.PHONY: help setup-local start-local stop-local test test-quick test-specific verify interactive clean

help:
	@echo "Sensing Garden Backend - Local Development"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup-local    - Set up local development environment"
	@echo "  make start-local    - Start LocalStack and local API server"
	@echo "  make stop-local     - Stop all local services"
	@echo "  make test          - Run full test suite with coverage"
	@echo "  make test-quick    - Run tests without coverage"
	@echo "  make verify        - Verify local setup is working"
	@echo "  make interactive   - Run interactive test interface"
	@echo "  make clean         - Clean up local data and containers"

setup-local:
	@echo "Setting up local development environment..."
	@echo "1. Installing Python dependencies..."
	pip install -r requirements-dev.txt
	@echo "2. Copying environment file..."
	@if [ ! -f .env.local ]; then \
		cp .env.local.example .env.local; \
		echo "Created .env.local - please update with your settings"; \
	else \
		echo ".env.local already exists"; \
	fi
	@echo "3. Creating local data directory..."
	mkdir -p local-data
	@echo "✓ Local setup complete!"

start-local:
	@echo "Starting local services..."
	@echo "1. Starting LocalStack..."
	docker-compose up -d localstack
	@echo "2. Waiting for LocalStack to be ready..."
	@sleep 5
	@echo "3. Setting up AWS resources..."
	docker-compose run --rm setup
	@echo "4. Starting local API server..."
	@echo ""
	@echo "LocalStack is running at http://localhost:4566"
	@echo "Starting API server at http://localhost:8000"
	@echo ""
	python run_local.py

stop-local:
	@echo "Stopping local services..."
	docker-compose down
	@echo "✓ Local services stopped"

test:
	@echo "Running tests..."
	@if [ ! -f .env.local ]; then \
		echo "Error: .env.local not found. Run 'make setup-local' first"; \
		exit 1; \
	fi
	@./run_tests.sh

test-quick:
	@echo "Running tests without coverage..."
	@export ENVIRONMENT=local && \
	export AWS_ENDPOINT_URL=http://localhost:4566 && \
	python -m pytest tests/ -v

test-specific:
	@echo "Running specific test file..."
	@echo "Usage: make test-specific TEST=tests/test_handler.py"
	@export ENVIRONMENT=local && \
	export AWS_ENDPOINT_URL=http://localhost:4566 && \
	python -m pytest $(TEST) -v -s

verify:
	@echo "Verifying local setup..."
	@./verify_local_setup.sh

interactive:
	@echo "Starting interactive test interface..."
	@python interactive_test.py

clean:
	@echo "Cleaning up..."
	docker-compose down -v
	rm -rf local-data/
	@echo "✓ Cleanup complete"