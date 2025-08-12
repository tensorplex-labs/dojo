CRUSH — local dev & style guide for agents

Build / Run / Test
- Build all binaries: make build
- Build single: make build-validator | make build-miner | make build-scoring
- Run (dev): make dev-<validator|miner|scoring|msg-server|msg-client|signature>
- Run built binary: make run-validator
- Tests (all): make test  (alias: go test ./...)
- Tests (single package): go test ./internal/scoring -v
- Single test: go test ./internal/scoring -run '^TestName$' -v
- Race/coverage: go test -race ./...  | go test -cover ./...
- Lint/format/typecheck: make lint  | make fmt | make vet
- Deps: make deps (go mod download && go mod tidy)

Code style (Go)
- Format: use gofmt/goimports; run make fmt before commits.
- Imports: stdlib first, blank line, external modules, then internal packages (let goimports decide order).
- Packages: short, singular, lowercase (e.g. scoring, miner, synapse).
- Names: Exported = PascalCase; unexported = camelCase. Keep receiver names short (r, s, m) and consistent.
- Types: use concrete types where helpful; prefer small interfaces local to the consumer.
- Context: pass context.Context as first parameter when used; do not store Context in structs.
- Errors: return errors; wrap with fmt.Errorf("msg: %w", err) or errors.Join/Wrap when appropriate. Do not log and return—log at top-level only.
- Panics: only in main, init, or tests. Prefer explicit error returns.
- Logging: use internal/utils/logger where available; keep logs structured and minimal in libraries.
- Tests: prefer table-driven tests and t.Run subtests; name tests Test<Thing> or Benchmark<Thing>.
- Concurrency: prefer channels/context for cancellation; use -race when testing concurrency.

Repo / agent rules
- CRUSH.md is the canonical local commands and style file; add useful commands here when discovered.
- .crush/ is ignored (already present in .gitignore). Do not commit secrets or environment files (.env).
- Cursor/Copilot rules: none found in .cursor or .github; if added, include brief summary here.

Commits & checks
- Run make fmt && make vet && make lint && go test ./... before committing changes.
- If adding a new dependency run make deps and check go.mod updated.
