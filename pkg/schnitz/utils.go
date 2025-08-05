package schnitz

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/gofiber/fiber/v2"
)

// createResponse creates a StdResponse with the given body and error
func createResponse[T any](body T, err error) StdResponse[T] {
	if err != nil {
		errMsg := err.Error()
		return StdResponse[T]{
			Body:  body,
			Error: &errMsg,
		}
	}
	return StdResponse[T]{
		Body:  body,
		Error: nil,
	}
}

// GetMessage extracts the specific headers from the request for your own
// business specific logic
func GetRequestContext(c *fiber.Ctx) *RequestContext {
	message := c.Get(string(MessageHeader))
	hotkey := c.Get(string(HotkeyHeader))
	signature := c.Get(string(SignatureHeader))
	
	return &RequestContext{
		c: c,
		Auth: AuthParams{
			Hotkey:    hotkey,
			Message:   message,
			Signature: signature,
		},
	}
}

// GetExternalIP gets the external IP address, useful for serving axons
func (s *Server) GetExternalIP() (string, error) {
	ipCheckServices := []struct {
		url    string
		parser func([]byte) (string, error)
	}{
		{
			"https://checkip.amazonaws.com",
			func(data []byte) (string, error) {
				return strings.TrimSpace(string(data)), nil
			},
		},
		{
			"https://api.ipify.org",
			func(data []byte) (string, error) {
				return strings.TrimSpace(string(data)), nil
			},
		},
		{
			"https://icanhazip.com",
			func(data []byte) (string, error) {
				return strings.TrimSpace(string(data)), nil
			},
		},
		{
			"https://ifconfig.me",
			func(data []byte) (string, error) {
				return strings.TrimSpace(string(data)), nil
			},
		},
	}

	client := &http.Client{}
	for _, service := range ipCheckServices {
		resp, err := client.Get(service.url)
		if err != nil {
			continue
		}

		if resp.StatusCode == http.StatusOK {
			body := make([]byte, IPReadBufferSize)
			n, err := resp.Body.Read(body)
			resp.Body.Close()

			if err == nil || n > 0 {
				ip, parseErr := service.parser(body[:n])
				if parseErr == nil {
					return ip, nil
				}
			}
		}
		resp.Body.Close()
	}

	return "", fmt.Errorf("all IP detection services failed")
}
