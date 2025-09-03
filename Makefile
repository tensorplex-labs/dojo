# Dojo v2 Makefile

# Variables
BINARY_DIR := bin
GO := go
GOFLAGS := -v
LDFLAGS := -s -w

# Binary names
VALIDATOR_BIN := $(BINARY_DIR)/validator
MINER_BIN := $(BINARY_DIR)/miner
SCORING_BIN := $(BINARY_DIR)/scoring
MSG_SERVER_BIN := $(BINARY_DIR)/msg-server
MSG_CLIENT_BIN := $(BINARY_DIR)/msg-client
SIGNATURE_BIN := $(BINARY_DIR)/signature

# Source paths
VALIDATOR_SRC := ./cmd/validator
MINER_SRC := ./cmd/miner
SCORING_SRC := ./cmd/scoring
MSG_SERVER_SRC := ./cmd/messaging/server
MSG_CLIENT_SRC := ./cmd/messaging/client
SIGNATURE_SRC := ./cmd/signature

.PHONY: all build clean test lint run-validator run-miner run-scoring run-msg-server run-msg-client run-signature preflight

# Default target
all: build

# Create binary directory
$(BINARY_DIR):
	mkdir -p $(BINARY_DIR)

# Build all binaries
build: $(BINARY_DIR) build-validator build-miner build-scoring build-messaging build-signature
	@echo "✅ All binaries built successfully"

# Individual build targets
build-validator: $(BINARY_DIR)
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(VALIDATOR_BIN) $(VALIDATOR_SRC)
	@echo "✅ Validator built: $(VALIDATOR_BIN)"

build-miner: $(BINARY_DIR)
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(MINER_BIN) $(MINER_SRC)
	@echo "✅ Miner built: $(MINER_BIN)"

build-scoring: $(BINARY_DIR)
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(SCORING_BIN) $(SCORING_SRC)
	@echo "✅ Scoring built: $(SCORING_BIN)"

build-messaging: build-msg-server build-msg-client

build-msg-server: $(BINARY_DIR)
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(MSG_SERVER_BIN) $(MSG_SERVER_SRC)
	@echo "✅ Message Server built: $(MSG_SERVER_BIN)"

build-msg-client: $(BINARY_DIR)
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(MSG_CLIENT_BIN) $(MSG_CLIENT_SRC)
	@echo "✅ Message Client built: $(MSG_CLIENT_BIN)"

build-signature: $(BINARY_DIR)
	$(GO) build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(SIGNATURE_BIN) $(SIGNATURE_SRC)
	@echo "✅ Signature tool built: $(SIGNATURE_BIN)"

# Run targets (builds if needed)
run-validator: build-validator
	$(VALIDATOR_BIN)

run-miner: build-miner
	$(MINER_BIN)

run-scoring: build-scoring
	$(SCORING_BIN)

run-msg-server: build-msg-server
	$(MSG_SERVER_BIN)

run-msg-client: build-msg-client
	$(MSG_CLIENT_BIN)

run-signature: build-signature
	$(SIGNATURE_BIN)

# Development targets
dev-validator:
	$(GO) run $(VALIDATOR_SRC)

dev-miner:
	$(GO) run $(MINER_SRC)

dev-scoring:
	$(GO) run $(SCORING_SRC)

dev-msg-server:
	$(GO) run $(MSG_SERVER_SRC)

dev-msg-client:
	$(GO) run $(MSG_CLIENT_SRC)

dev-signature:
	$(GO) run $(SIGNATURE_SRC)

# Testing
test:
	$(GO) test ./...

test-verbose:
	$(GO) test -v ./...

test-coverage:
	$(GO) test -cover ./...

test-race:
	$(GO) test -race ./...

# Linting
lint:
	golangci-lint run

lint-fix:
	golangci-lint run --fix

# Cleanup
clean:
	rm -rf $(BINARY_DIR)
	$(GO) clean
	@echo "🧹 Cleaned build artifacts"

# Dependencies
deps:
	$(GO) mod download
	$(GO) mod tidy

# Format code
fmt:
	$(GO) fmt ./...
	@echo "✨ Code formatted"

# Vet code
vet:
	$(GO) vet ./...
	@echo "🔍 Code vetted"

# Preflight (ensure lefthook installed and hooks set up)
preflight:
	@command -v lefthook >/dev/null 2>&1 || (echo "Installing lefthook..." && $(GO) install github.com/evilmartians/lefthook@latest)
	@lefthook install

# Quick check (preflight, format, vet, lint, test)
check: preflight fmt vet lint test
	@echo "✅ All checks passed"

# Install binaries to GOPATH/bin
install: build
	cp $(VALIDATOR_BIN) $(GOPATH)/bin/dojo-validator
	cp $(MINER_BIN) $(GOPATH)/bin/dojo-miner
	cp $(SCORING_BIN) $(GOPATH)/bin/dojo-scoring
	cp $(MSG_SERVER_BIN) $(GOPATH)/bin/dojo-msg-server
	cp $(MSG_CLIENT_BIN) $(GOPATH)/bin/dojo-msg-client
	cp $(SIGNATURE_BIN) $(GOPATH)/bin/dojo-signature
	@echo "✅ Binaries installed to $(GOPATH)/bin"

# Help target
help:
	@echo "Dojo v2 Makefile"
	@echo ""
	@echo "Build targets:"
	@echo "  make build              - Build all binaries"
	@echo "  make build-validator    - Build validator binary"
	@echo "  make build-miner        - Build miner binary"
	@echo "  make build-scoring      - Build scoring binary"
	@echo "  make build-messaging    - Build messaging server and client"
	@echo "  make build-signature    - Build signature tool"
	@echo ""
	@echo "Run targets (builds first):"
	@echo "  make run-validator      - Build and run validator"
	@echo "  make run-miner          - Build and run miner"
	@echo "  make run-scoring        - Build and run scoring"
	@echo "  make run-msg-server     - Build and run message server"
	@echo "  make run-msg-client     - Build and run message client"
	@echo "  make run-signature      - Build and run signature tool"
	@echo ""
	@echo "Development targets (no build):"
	@echo "  make dev-validator      - Run validator with go run"
	@echo "  make dev-miner          - Run miner with go run"
	@echo "  make dev-scoring        - Run scoring with go run"
	@echo "  make dev-msg-server     - Run message server with go run"
	@echo "  make dev-msg-client     - Run message client with go run"
	@echo "  make dev-signature      - Run signature tool with go run"
	@echo ""
	@echo "Quality targets:"
	@echo "  make test               - Run tests"
	@echo "  make test-verbose       - Run tests with verbose output"
	@echo "  make test-coverage      - Run tests with coverage"
	@echo "  make test-race          - Run tests with race detector"
	@echo "  make lint               - Run linter"
	@echo "  make lint-fix           - Run linter with auto-fix"
	@echo "  make fmt                - Format code"
	@echo "  make vet                - Vet code"
	@echo "  make check              - Run all checks (fmt, vet, lint, test)"
	@echo ""
	@echo "Other targets:"
	@echo "  make clean              - Remove build artifacts"
	@echo "  make deps               - Download and tidy dependencies"
	@echo "  make install            - Install binaries to GOPATH/bin"
	@echo "  make help               - Show this help message"