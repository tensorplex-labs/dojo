# Build the validator binary and produce a minimal runtime image.

# Builder stage: compile the Go binary
FROM golang:1.24-alpine AS builder

WORKDIR /src
RUN apk add --no-cache git ca-certificates

# Download dependencies first for better build caching
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the source and build the validator
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags='-s -w' -o /out/validator ./cmd/validator

# Final image: small Alpine with CA certs
FROM alpine:3.18
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /out/validator ./validator
RUN chmod +x ./validator

ENV PATH="/app:${PATH}"

CMD ["/app/validator"]
