package schnitz

import (
	"errors"
	"fmt"
	"os"
	"reflect"
	"strconv"

	"github.com/bytedance/sonic"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/compress"
	"github.com/gofiber/fiber/v2/middleware/recover"

	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/pkg/signature"
)

// NewServer creates a new messaging server
func NewServer(serverConfig *ServerConfig) *Server {
	if serverConfig == nil {
		serverConfig = &ServerConfig{
			Host:      DefaultServerHost,
			Port:      DefaultServerPort,
			BodyLimit: DefaultBodyLimit,
		}
	}

	// Load configuration from environment variables
	if serverConfig.Port == 0 || serverConfig.Port == DefaultServerPort {
		if portStr := os.Getenv("SERVER_PORT"); portStr != "" {
			if port, err := strconv.Atoi(portStr); err == nil {
				serverConfig.Port = port
				log.Debug().
					Int("port", port).
					Msg("Loaded server port from environment")
			} else {
				log.Warn().
					Str("SERVER_PORT", portStr).
					Err(err).
					Msg("Invalid SERVER_PORT environment variable, using default")
			}
		}
	}

	if serverConfig.BodyLimit == 0 || serverConfig.BodyLimit == DefaultBodyLimit {
		if bodyLimitStr := os.Getenv("SERVER_BODY_LIMIT"); bodyLimitStr != "" {
			if bodyLimit, err := strconv.Atoi(bodyLimitStr); err == nil {
				serverConfig.BodyLimit = bodyLimit
				log.Debug().
					Int("body_limit", bodyLimit).
					Msg("Loaded server body limit from environment")
			} else {
				log.Warn().
					Str("SERVER_BODY_LIMIT", bodyLimitStr).
					Err(err).
					Msg("Invalid SERVER_BODY_LIMIT environment variable, using default")
			}
		}
	}

	log.Info().
		Any("serverConfig", serverConfig).
		Msg("Server configuration loaded")

	app := fiber.New(fiber.Config{
		Prefork:      false,
		ErrorHandler: fiberErrHandler,
		JSONEncoder:  sonic.Marshal,
		JSONDecoder:  sonic.Unmarshal,
		BodyLimit:    serverConfig.BodyLimit,
	})

	app.Use(recover.New()) // add panic recovery
	app.Use(compress.New(compress.Config{Level: compress.LevelBestCompression}))

	server := &Server{
		App:    app,
		config: serverConfig,
	}

	// Add middleware using standalone functions
	whitelistedRoutes := []string{"/docs", "/health"}
	app.Use(ZstdMiddleware(whitelistedRoutes))
	app.Use(SignatureMiddleware(signature.NewVerifier(), whitelistedRoutes))

	return server
}

func fiberErrHandler(ctx *fiber.Ctx, err error) error {
	// Status code defaults to 500
	code := fiber.StatusInternalServerError

	// Retrieve the custom status code if it's a *fiber.Error
	var e *fiber.Error
	if errors.As(err, &e) {
		code = e.Code
	}

	log.Error().
		Err(err).
		Int("status_code", code).
		Str("path", ctx.Path()).
		Str("method", ctx.Method()).
		Msg("Fiber error handler triggered")

	return ctx.Status(code).JSON(createResponse(map[string]interface{}{}, err))
}

// ServeRoute registers a handler for a specific type T
func ServeRoute[T any](s *Server, handler RouterHandler[T]) {
	var zero T
	typeName := reflect.TypeOf(zero).Name()

	s.App.Post("/"+typeName, func(c *fiber.Ctx) error {
		var req T
		if err := c.BodyParser(&req); err != nil {
			log.Error().
				Err(err).
				Str("route", "/"+typeName).
				Msg("Failed to parse request body")
			return c.Status(fiber.StatusBadRequest).
				JSON(createResponse(map[string]interface{}{}, err))
		}

		resp, err := handler(c, req)
		if err != nil {
			log.Error().
				Err(err).
				Str("route", "/"+typeName).
				Msg("Handler returned error")
			var zero T
			return c.Status(fiber.StatusInternalServerError).JSON(createResponse(zero, err))
		}

		return c.JSON(createResponse(resp, nil))
	})
}

func (s Server) Start() {
	portStr := fmt.Sprintf(":%d", s.config.Port)
	log.Fatal().
		Err(s.App.Listen(portStr)).
		Msg("Server failed to start")
}
