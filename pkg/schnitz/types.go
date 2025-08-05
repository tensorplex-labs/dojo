package schnitz

import (
	"github.com/gofiber/fiber/v2"
)

type (
	ID        string
	Timestamp int64
)

const (
	SignatureHeader string = "x-signature"
	HotkeyHeader    string = "x-hotkey"
	MessageHeader   string = "x-message"

	// Server defaults
	DefaultServerHost = "0.0.0.0"
	DefaultServerPort = 8888
	DefaultBodyLimit  = 4 * 1024 * 1024 // 4MB

	// Client defaults
	DefaultClientTimeout = 30 // seconds

	// Utility constants
	IPReadBufferSize = 1024
)

// Server represents the messaging server
type Server struct {
	App    *fiber.App
	config *ServerConfig
}

type ServerConfig struct {
	Host      string
	Port      int
	BodyLimit int
}

// StdResponse represents the standardized response structure
type StdResponse[T any] struct {
	Body  T       `json:"body"`
	Error *string `json:"error,omitempty"`
}

// AuthParams holds authentication parameters for requests
type AuthParams struct {
	Hotkey    string `validate:"required,len=48"`
	Message   string `validate:"required,min=1"`
	Signature string `validate:"required,startswith=0x,len=130"`
}

// RequestContext wraps fiber.Ctx to provide easy header access
type RequestContext struct {
	c    *fiber.Ctx
	Auth AuthParams
}

// RouterHandler is a generic handler function type
type RouterHandler[T any] func(*fiber.Ctx, T) (T, error)

