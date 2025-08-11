package synapse

import (
	"bytes"
	"fmt"
	"io"
	"strconv"
	"strings"

	"github.com/gofiber/fiber/v3"
	"github.com/klauspost/compress/zstd"
	"github.com/rs/zerolog/log"
	"github.com/tensorplex-labs/dojo/internal/kami"
)

// ZstdMiddleware returns a Fiber middleware that decompresses incoming request
// bodies with Content-Encoding: zstd and, when the client accepts zstd, compresses
// the outgoing response with zstd.
func ZstdMiddleware() fiber.Handler {
	return func(c fiber.Ctx) error {
		// Decompress request body if encoded with zstd
		if strings.Contains(strings.ToLower(c.Get("Content-Encoding")), "zstd") {
			r, err := zstd.NewReader(bytes.NewReader(c.Body()))
			if err != nil {
				log.Error().Err(err).Msg("zstd: failed to create reader for request body")
				return c.Status(fiber.StatusBadRequest).SendString("invalid zstd request body")
			}
			defer r.Close()

			out, err := io.ReadAll(r)
			if err != nil {
				log.Error().Err(err).Msg("zstd: failed to decompress request body")
				return c.Status(fiber.StatusBadRequest).SendString("invalid zstd request body")
			}

			c.Request().SetBody(out)
			c.Request().Header.Set("Content-Length", strconv.Itoa(len(out)))
			c.Request().Header.Del("Content-Encoding")
		}

		// Continue to next handler
		if err := c.Next(); err != nil {
			return err
		}

		// Compress response if client accepts zstd
		if strings.Contains(strings.ToLower(c.Get("Accept-Encoding")), "zstd") {
			respBody := c.Response().Body()
			var buf bytes.Buffer
			w, err := zstd.NewWriter(&buf)
			if err != nil {
				log.Error().Err(err).Msg("zstd: failed to create writer for response body")
				return nil
			}
			if _, err := w.Write(respBody); err != nil {
				_ = w.Close()
				log.Error().Err(err).Msg("zstd: failed to compress response body")
				return nil
			}
			_ = w.Close()

			comp := buf.Bytes()
			c.Response().SetBody(comp)
			c.Set("Content-Encoding", "zstd")
			c.Set("Vary", "Accept-Encoding")
			c.Set("Content-Length", strconv.Itoa(len(comp)))
		}

		return nil
	}
}

// VerifySignatureMiddleware verifies requests contain valid signatures in headers.
// Requires headers: x-signature, x-hotkey, x-timestamp. Uses kami.VerifyMessage to validate.
func VerifySignatureMiddleware(k *kami.Kami) fiber.Handler {
	return func(c fiber.Ctx) error {
		sig := c.Get("x-signature")
		hotkey := c.Get("x-hotkey")
		timestamp := c.Get("x-timestamp") // in seconds, not milliseconds e.g. 1700000000 not 1700000000000
		if sig == "" || hotkey == "" {
			log.Warn().Bool("missing_sig", sig == "").Bool("missing_hotkey", hotkey == "").Msg("missing signature or hotkey header")
			return c.Status(fiber.StatusUnauthorized).SendString("missing signature or hotkey header")
		}

		// read body (already decompressed by zstd middleware if used)
		// body := c.Body()

		params := kami.VerifyMessageParams{
			Message:       fmt.Sprintf("%s.%s.i am real and dojo is real, please verify me!", hotkey, timestamp),
			Signature:     sig,
			SigneeAddress: hotkey,
		}

		res, err := k.VerifyMessage(params)
		if err != nil {
			log.Error().Err(err).Msg("kami: verify message failed")
			return c.Status(fiber.StatusUnauthorized).SendString("signature verification error")
		}

		if !res.Data.Valid {
			log.Warn().Str("hotkey", hotkey).Msg("invalid signature")
			return c.Status(fiber.StatusUnauthorized).SendString("invalid signature")
		}

		return c.Next()
	}
}
