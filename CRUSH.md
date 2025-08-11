# CRUSH — repository helper

Build / run / test
- make build           # build all binaries (Makefile targets)
- make build-<name>    # build-validator / build-miner / build-scoring / build-messaging / build-signature
- make run-<name>      # build & run
- make fmt              # go fmt ./...
- make lint             # golangci-lint run
- make test             # go test ./...
- Single test: go test ./path/to/pkg -run '^TestName$' -v
- Coverage / race: go test -cover ./...  | go test -race ./...

Quality checks
- Formatting: gofmt / goimports; run `make fmt` before commits
- Vet: go vet ./... (make vet)
- Lint: golangci-lint (config at .golangci.yml)

Code style (Go)
- Imports: group stdlib, blank line, third-party, blank line, internal packages; keep unused imports removed
- Formatting: rely on gofmt/goimports; keep lines reasonably short
- Naming: Exported identifiers CamelCase; unexported mixedCase; package names short, singular (e.g., scoring, synapse)
- Types: prefer concrete types; use interfaces for behaviour only (for tests/mocks)
- Errors: check errors immediately, return early; wrap with fmt.Errorf("%w") when adding context
- Context: accept context.Context as first arg in public functions that do I/O or long-running work
- Logging: use internal/utils/logger package; keep logs structured and minimal in libraries
- Tests: table-driven tests, small focused cases; avoid network or heavy external deps in unit tests (use interfaces/mocks)
- Concurrency: prefer channels + context cancellation; prefer deterministic tests (use t.Parallel only when safe)

Repo notes
- Go modules: go.mod is authoritative; use `make deps` for dependency tasks
- Lint config: .golangci.yml present; follow it
- .crush/ is already ignored in .gitignore

Editor/assist rules
- No Cursor/Copilot rules found in .cursor/ or .github/copilot-instructions.md

This file is intended for agentic tools operating on this repo: run `make check` before pushing changes.