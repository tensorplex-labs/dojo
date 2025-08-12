package synapse

import (
	"context"
	"time"

	"github.com/bytedance/sonic"
	"github.com/gofiber/fiber/v3"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/kami"
)

type Server struct {
	app *fiber.App
	cfg Config
}

func NewServer(cfg Config, kami *kami.Kami) *Server {
	app := fiber.New()

	app.Use(ZstdMiddleware())
	app.Use(VerifySignatureMiddleware(kami))

	s := &Server{app: app, cfg: cfg}
	app.Post("/heartbeat", s.handleHeartbeat)
	return s
}

func (s *Server) handleHeartbeat(c fiber.Ctx) error {
	var hb HeartbeatRequest
	if err := sonic.Unmarshal(c.Body(), &hb); err != nil {
		log.Error().Err(err).Msg("failed to unmarshal heartbeat")
		return c.Status(fiber.StatusBadRequest).JSON(HeartbeatResponse{Status: "error", Message: "invalid payload"})
	}

	log.Info().Str("Validator Hotkey", hb.ValidatorHotkey).Int64("timestamp", hb.Timestamp).Msg("receive heartbeat")

	resp := HeartbeatResponse{Status: "ok", ReceivedAt: time.Now().UnixNano(), Message: "heartbeat received"}
	return c.Status(fiber.StatusOK).JSON(resp)
}

func (s *Server) Start(ctx context.Context) error {
	go func() {
		if err := s.app.Listen(s.cfg.Address); err != nil {
			log.Error().Err(err).Msg("server listen failed")
		}
	}()
	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	return s.Shutdown(shutdownCtx)
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.app.Shutdown()
}
