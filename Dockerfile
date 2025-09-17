# syntax=docker/dockerfile:1.6
# Multi-arch Dockerfile that builds a single app binary per image based on APP_NAME

FROM golang:1.24-alpine AS builder
ARG TARGETOS
ARG TARGETARCH
ARG APP_NAME=validator

WORKDIR /src
RUN apk add --no-cache git ca-certificates

# Download dependencies first for better build caching
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the source and build the selected app
COPY . .
RUN CGO_ENABLED=0 GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} \
    go build -ldflags='-s -w' -o /out/app ./cmd/${APP_NAME}

# Final image: small Alpine with CA certs
FROM alpine:3.18
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /out/app ./app
RUN chmod +x ./app

ENV PATH="/app:${PATH}"

ENTRYPOINT ["/app/app"]
