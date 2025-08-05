package schnitz

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/gofiber/fiber/v2"
	"github.com/klauspost/compress/zstd"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/pkg/signature"
)

// ZstdMiddleware is a standalone middleware function that can be used independently
func ZstdMiddleware(whitelistedRoutes []string) fiber.Handler {
	if whitelistedRoutes == nil {
		whitelistedRoutes = []string{"/docs", "/health"}
		log.Debug().
			Any("default", whitelistedRoutes).
			Msg("Whitelisted routes not specified, using default whitelist")
	}

	return func(c *fiber.Ctx) error {
		path := c.Path()

		// Check if route is whitelisted
		for _, route := range whitelistedRoutes {
			if path == route {
				return c.Next()
			}
		}

		// Handle request decompression
		contentEncoding := c.Get("content-encoding")
		if strings.ToLower(contentEncoding) == "zstd" {
			body := c.Body()
			if len(body) > 0 {
				decoder, err := zstd.NewReader(bytes.NewReader(body))
				if err != nil {
					log.Err(err).Msg("Failed to create zstd decoder")
					return c.Status(fiber.StatusBadRequest).JSON(
						createResponse(
							map[string]interface{}{},
							fmt.Errorf("Failed to decompress zstd data: %s", err.Error()),
						))
				}
				defer decoder.Close()

				decompressed, err := io.ReadAll(decoder)
				if err != nil {
					log.Err(err).Msg("Failed to decompress request")
					return c.Status(fiber.StatusBadRequest).JSON(
						createResponse(
							map[string]interface{}{},
							fmt.Errorf("Failed to decompress zstd data: %s", err.Error()),
						))
				}

				c.Request().SetBody(decompressed)
				log.Debug().Msg("Request body decompressed")
			}
		}

		// Process the request
		err := c.Next()
		if err != nil {
			return err
		}

		// Handle response compression
		acceptEncoding := c.Get("accept-encoding")
		if strings.Contains(strings.ToLower(acceptEncoding), "zstd") {
			responseBody := c.Response().Body()
			if len(responseBody) > 0 {
				encoder, err := zstd.NewWriter(nil, zstd.WithEncoderLevel(zstd.SpeedDefault))
				if err != nil {
					log.Err(err).Msg("Failed to create zstd encoder")
					return nil // Continue without compression
				}
				defer encoder.Close()

				compressed := encoder.EncodeAll(responseBody, nil)
				c.Response().SetBody(compressed)
				c.Set("content-encoding", "zstd")
				c.Set("content-length", fmt.Sprintf("%d", len(compressed)))

				log.Debug().
					Int("original_size", len(responseBody)).
					Int("compressed_size", len(compressed)).
					Msg("Response body compressed")
			}
		}

		return nil
	}
}

// SignatureMiddleware is a standalone middleware function for signature verification
func SignatureMiddleware(signatureVerifier signature.SignatureVerifier, whitelistedRoutes []string) fiber.Handler {
	if whitelistedRoutes == nil {
		whitelistedRoutes = []string{"/docs", "/health"}
		log.Debug().
			Any("default", whitelistedRoutes).
			Msg("Whitelisted routes not specified, using default whitelist")
	}

	return func(c *fiber.Ctx) error {
		path := c.Path()

		log.Info().Str("path", path).Msg("SignatureMiddleware running")
		// Check if route is whitelisted
		for _, route := range whitelistedRoutes {
			if path == route {
				return c.Next()
			}
		}

		// Extract headers
		sig := c.Get(SignatureHeader)
		hotkey := c.Get(HotkeyHeader)
		message := c.Get(MessageHeader)

		// Validate headers presence
		if hotkey == "" || sig == "" || message == "" {
			errMsg := fmt.Sprintf("%s, missing headers, expected: %s, %s, %s",
				http.StatusText(http.StatusBadRequest),
				SignatureHeader, HotkeyHeader, MessageHeader)
			return c.Status(fiber.StatusBadRequest).JSON(
				createResponse(map[string]interface{}{}, fmt.Errorf("%s", errMsg)))
		}

		// Verify signature
		isSignatureValid, err := signatureVerifier.Verify(message, sig, hotkey)
		if err != nil {
			errMsg := fmt.Sprintf("Signature verification error: %s", err.Error())
			return c.Status(fiber.StatusInternalServerError).JSON(
				createResponse(map[string]interface{}{}, fmt.Errorf("%s", errMsg)))
		}

		if !isSignatureValid {
			errMsg := fmt.Sprintf(
				"%s due to invalid signature",
				http.StatusText(http.StatusForbidden),
			)
			return c.Status(fiber.StatusForbidden).JSON(
				createResponse(map[string]interface{}{}, fmt.Errorf("%s", errMsg)))
		}

		log.Info().
			Bool("isSignatureValid", isSignatureValid).
			Str("hotkey", hotkey).
			Str("signature", sig).
			Str("message", message).
			Msg("Verified signature successfully")

		return c.Next()
	}
}
