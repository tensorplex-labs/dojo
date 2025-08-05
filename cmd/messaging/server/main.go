package main

import (
	"errors"
	"os"

	"github.com/joho/godotenv"
	schnitz "github.com/tensorplex-labs/dojo/pkg/schnitz"

	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

type CalculateRequest struct {
	A int `json:"a"`
	B int `json:"b"`
}

type UserRequest struct {
	Name  string `json:"name"`
	Email string `json:"email"`
}

func main() {
	// Configure zerolog for human-readable output
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})
	err := godotenv.Load()
	if err != nil {
		log.Fatal().Msg("Error loading .env file")
	}

	log.Info().Msg("Starting messaging server test...")

	// Create server with custom config
	serverConfig := &schnitz.ServerConfig{
		Host: "0.0.0.0",
		Port: 8888,
	}
	server := schnitz.NewServer(serverConfig)

	// Register test routes using ServeRoute
	// 1. Ping route - POST /PingRequest
	schnitz.ServeRoute(
		server,
		func(c *fiber.Ctx, req schnitz.PingRequest) (schnitz.PingRequest, error) {
			log.Info().Any("request", req).Msg("Ping handler called")
			return schnitz.PingRequest{Message: "pong: " + req.Message}, nil
		},
	)

	// 2. User route - POST /UserRequest
	schnitz.ServeRoute(server, func(c *fiber.Ctx, req UserRequest) (UserRequest, error) {
		log.Info().Any("request", req).Msg("User handler called")
		if req.Name == "" {
			return req, errors.New("name is required")
		}
		req.Name = req.Name
		return req, nil
	})

	// 3. Calculate route - POST /CalculateRequest
	schnitz.ServeRoute(
		server,
		func(c *fiber.Ctx, req CalculateRequest) (CalculateRequest, error) {
			log.Info().Any("request", req).Msg("Calculate handler called")
			if req.B == 0 {
				return req, errors.New("division by zero")
			}
			req.A = req.A + req.B // Simple addition
			return req, nil
		},
	)

	log.Info().
		Str("host", serverConfig.Host).
		Int("port", serverConfig.Port).
		Msg("Server starting")
	log.Info().Msg("Test endpoints:")
	log.Info().Msg("  POST /PingRequest")
	log.Info().Msg("  POST /UserRequest")
	log.Info().Msg("  POST /CalculateRequest")
	log.Info().Msg("  GET /health")

	// Start server
	server.Start()
}
