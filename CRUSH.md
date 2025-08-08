# CRUSH.md - Repo helper for agents

# Commands
# Run all tests
go test ./...
# Run single test by name (package path optional)
# Example: go test -run '^TestMyFunc$' ./pkg/signature
# Verbose and race detector
go test -v -race ./...
# Run coverage for a package
go test -coverprofile=cover.out ./pkg/signature && go tool cover -html=cover.out
# Lint and vet
golangci-lint run
go vet ./...

# Style & Guidelines
- Logging: always use zerolog/log; never use the stdlib log package.
- JSON: use bytedance/sonic for marshal/unmarshal (sonic.Marshal / sonic.Unmarshal).
- Constants: avoid magic numbers; define named constants in a package types.go.
- Types & interfaces: place package-level types, interfaces, and constants in types.go files.
- Config: create config structs and load env vars in NewServer/NewClient (confirm env var names with repo owner). Document them in .env.example and README.md.
- Imports: group imports in three blocks: standard library, third-party, local (github.com/<org>/<repo>).
- Errors: check every error, wrap with fmt.Errorf("...: %w", err) when adding context; avoid panics in library code.
- Tests: prefer testify (assert/suite); keep tests deterministic and small.
- Formatting: gofmt/golangci-lint on save; keep lines under 120 chars and functions concise.
- Cursor/Copilot rules: none found in .cursor/rules/ or .cursorrules or .github/copilot-instructions.md.
