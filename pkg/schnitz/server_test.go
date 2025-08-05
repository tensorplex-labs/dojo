package schnitz

import (
	"bytes"
	"errors"
	"io"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/bytedance/sonic"
	"github.com/gofiber/fiber/v2"
)

// Mock signature verifier for testing
type MockSignatureVerifier struct {
	shouldVerify bool
	shouldError  bool
}

func (m *MockSignatureVerifier) Verify(message, signature, hotkey string) (bool, error) {
	if m.shouldError {
		return false, errors.New("verification error")
	}
	return m.shouldVerify, nil
}

func TestNewServer(t *testing.T) {
	t.Run("creates server with default config when nil config passed", func(t *testing.T) {
		server := NewServer(nil)

		if server == nil {
			t.Fatal("Expected server to be created, got nil")
		}

		if server.App == nil {
			t.Error("Expected server.App to be initialized")
		}

		if server.config == nil {
			t.Error("Expected server.config to be initialized")
		}

		// Check default values
		if server.config.Host != DefaultServerHost {
			t.Errorf("Expected host %s, got %s", DefaultServerHost, server.config.Host)
		}
		if server.config.Port != DefaultServerPort {
			t.Errorf("Expected port %d, got %d", DefaultServerPort, server.config.Port)
		}
		if server.config.BodyLimit != DefaultBodyLimit {
			t.Errorf("Expected body limit %d, got %d", DefaultBodyLimit, server.config.BodyLimit)
		}
	})

	t.Run("uses provided config when passed", func(t *testing.T) {
		config := &ServerConfig{
			Host:      "127.0.0.1",
			Port:      9999,
			BodyLimit: 1024,
		}

		server := NewServer(config)

		if server.config.Host != config.Host {
			t.Errorf("Expected host %s, got %s", config.Host, server.config.Host)
		}
		if server.config.Port != config.Port {
			t.Errorf("Expected port %d, got %d", config.Port, server.config.Port)
		}
		if server.config.BodyLimit != config.BodyLimit {
			t.Errorf("Expected body limit %d, got %d", config.BodyLimit, server.config.BodyLimit)
		}
	})

	t.Run("loads port from environment variable", func(t *testing.T) {
		// Set environment variable
		os.Setenv("SERVER_PORT", "7777")
		defer os.Unsetenv("SERVER_PORT")

		server := NewServer(nil)

		if server.config.Port != 7777 {
			t.Errorf("Expected port 7777 from env var, got %d", server.config.Port)
		}
	})

	t.Run("loads body limit from environment variable", func(t *testing.T) {
		// Set environment variable
		os.Setenv("SERVER_BODY_LIMIT", "2048")
		defer os.Unsetenv("SERVER_BODY_LIMIT")

		server := NewServer(nil)

		if server.config.BodyLimit != 2048 {
			t.Errorf("Expected body limit 2048 from env var, got %d", server.config.BodyLimit)
		}
	})

	t.Run("uses default port when env var is invalid", func(t *testing.T) {
		// Set invalid environment variable
		os.Setenv("SERVER_PORT", "invalid")
		defer os.Unsetenv("SERVER_PORT")

		server := NewServer(nil)

		if server.config.Port != DefaultServerPort {
			t.Errorf(
				"Expected default port %d when env var invalid, got %d",
				DefaultServerPort,
				server.config.Port,
			)
		}
	})

	t.Run("uses default body limit when env var is invalid", func(t *testing.T) {
		// Set invalid environment variable
		os.Setenv("SERVER_BODY_LIMIT", "invalid")
		defer os.Unsetenv("SERVER_BODY_LIMIT")

		server := NewServer(nil)

		if server.config.BodyLimit != DefaultBodyLimit {
			t.Errorf(
				"Expected default body limit %d when env var invalid, got %d",
				DefaultBodyLimit,
				server.config.BodyLimit,
			)
		}
	})

	t.Run("preserves non-default config values when env vars not set", func(t *testing.T) {
		config := &ServerConfig{
			Host:      "192.168.1.1",
			Port:      5555,
			BodyLimit: 512,
		}

		server := NewServer(config)

		if server.config.Port != 5555 {
			t.Errorf("Expected port 5555, got %d", server.config.Port)
		}
		if server.config.BodyLimit != 512 {
			t.Errorf("Expected body limit 512, got %d", server.config.BodyLimit)
		}
	})
}

func TestFiberErrHandler(t *testing.T) {
	t.Run("handles fiber.Error correctly", func(t *testing.T) {
		// Create a test server to get a proper fiber context
		server := NewServer(&ServerConfig{
			Host:      "localhost",
			Port:      8080,
			BodyLimit: DefaultBodyLimit,
		})

		// Add a test route that will trigger the error handler in whitelisted path
		server.App.Get("/health", func(c *fiber.Ctx) error {
			return fiber.NewError(fiber.StatusBadRequest, "test error")
		})

		// Create HTTP request
		req := httptest.NewRequest("GET", "/health", nil)

		// Execute request
		resp, err := server.App.Test(req)
		if err != nil {
			t.Fatalf("Failed to execute request: %v", err)
		}

		// Check response
		if resp.StatusCode != fiber.StatusBadRequest {
			t.Errorf("Expected status code %d, got %d", fiber.StatusBadRequest, resp.StatusCode)
		}

		// Check response body
		respBody, _ := io.ReadAll(resp.Body)
		var response StdResponse[map[string]interface{}]
		if err := sonic.Unmarshal(respBody, &response); err != nil {
			t.Errorf("Failed to unmarshal response: %v", err)
		}

		if response.Error == nil {
			t.Error("Expected error in response")
		}

		if *response.Error != "test error" {
			t.Errorf("Expected error message 'test error', got '%s'", *response.Error)
		}
	})

	t.Run("handles generic error correctly", func(t *testing.T) {
		// Create a test server to get a proper fiber context
		server := NewServer(&ServerConfig{
			Host:      "localhost",
			Port:      8080,
			BodyLimit: DefaultBodyLimit,
		})

		// Add a test route that will trigger the error handler in whitelisted path
		server.App.Post("/docs", func(c *fiber.Ctx) error {
			return errors.New("generic error")
		})

		// Create HTTP request
		req := httptest.NewRequest("POST", "/docs", nil)

		// Execute request
		resp, err := server.App.Test(req)
		if err != nil {
			t.Fatalf("Failed to execute request: %v", err)
		}

		// Check response
		if resp.StatusCode != fiber.StatusInternalServerError {
			t.Errorf(
				"Expected status code %d, got %d",
				fiber.StatusInternalServerError,
				resp.StatusCode,
			)
		}

		// Check response body
		respBody, _ := io.ReadAll(resp.Body)
		var response StdResponse[map[string]interface{}]
		if err := sonic.Unmarshal(respBody, &response); err != nil {
			t.Errorf("Failed to unmarshal response: %v", err)
		}

		if response.Error == nil {
			t.Error("Expected error in response")
		}

		if *response.Error != "generic error" {
			t.Errorf("Expected error message 'generic error', got '%s'", *response.Error)
		}
	})
}

// Test struct for ServeRoute testing
type TestRequest struct {
	Name  string `json:"name"`
	Value int    `json:"value"`
}

// Helper function to create a server without middleware for testing ServeRoute
func createTestServerWithoutMiddleware() *Server {
	config := &ServerConfig{
		Host:      "localhost",
		Port:      8080,
		BodyLimit: DefaultBodyLimit,
	}

	// Create a minimal server without middleware
	app := fiber.New(fiber.Config{
		ErrorHandler: fiberErrHandler,
		BodyLimit:    config.BodyLimit,
	})

	return &Server{
		App:    app,
		config: config,
	}
}

func TestServeRoute(t *testing.T) {
	t.Run("registers route and handles successful request", func(t *testing.T) {
		server := createTestServerWithoutMiddleware()

		// Register a test handler
		ServeRoute(server, func(c *fiber.Ctx, req TestRequest) (TestRequest, error) {
			// Return the request with modified value
			req.Value = req.Value * 2
			return req, nil
		})

		// Create test request
		testReq := TestRequest{
			Name:  "test",
			Value: 5,
		}
		body, _ := sonic.Marshal(testReq)

		// Create HTTP request
		req := httptest.NewRequest("POST", "/TestRequest", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")

		// Execute request
		resp, err := server.App.Test(req)
		if err != nil {
			t.Fatalf("Failed to execute request: %v", err)
		}

		// Check response
		if resp.StatusCode != fiber.StatusOK {
			t.Errorf("Expected status code %d, got %d", fiber.StatusOK, resp.StatusCode)
		}

		// Parse response body
		respBody, _ := io.ReadAll(resp.Body)
		var response StdResponse[TestRequest]
		if err := sonic.Unmarshal(respBody, &response); err != nil {
			t.Errorf("Failed to unmarshal response: %v", err)
		}

		if response.Error != nil {
			t.Errorf("Expected no error in response, got %s", *response.Error)
		}

		if response.Body.Name != "test" {
			t.Errorf("Expected name 'test', got '%s'", response.Body.Name)
		}

		if response.Body.Value != 10 {
			t.Errorf("Expected value 10, got %d", response.Body.Value)
		}
	})

	t.Run("handles invalid JSON request body", func(t *testing.T) {
		server := createTestServerWithoutMiddleware()

		// Register a test handler
		ServeRoute(server, func(c *fiber.Ctx, req TestRequest) (TestRequest, error) {
			return req, nil
		})

		// Create HTTP request with invalid JSON
		req := httptest.NewRequest("POST", "/TestRequest", bytes.NewReader([]byte("invalid json")))
		req.Header.Set("Content-Type", "application/json")

		// Execute request
		resp, err := server.App.Test(req)
		if err != nil {
			t.Fatalf("Failed to execute request: %v", err)
		}

		// Check response
		if resp.StatusCode != fiber.StatusBadRequest {
			t.Errorf("Expected status code %d, got %d", fiber.StatusBadRequest, resp.StatusCode)
		}

		// Parse response body
		respBody, _ := io.ReadAll(resp.Body)
		var response StdResponse[map[string]interface{}]
		if err := sonic.Unmarshal(respBody, &response); err != nil {
			t.Errorf("Failed to unmarshal response: %v", err)
		}

		if response.Error == nil {
			t.Error("Expected error in response")
		}
	})

	t.Run("handles handler error", func(t *testing.T) {
		server := createTestServerWithoutMiddleware()

		// Register a test handler that returns an error
		ServeRoute(server, func(c *fiber.Ctx, req TestRequest) (TestRequest, error) {
			return TestRequest{}, errors.New("handler error")
		})

		// Create test request
		testReq := TestRequest{
			Name:  "test",
			Value: 5,
		}
		body, _ := sonic.Marshal(testReq)

		// Create HTTP request
		req := httptest.NewRequest("POST", "/TestRequest", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")

		// Execute request
		resp, err := server.App.Test(req)
		if err != nil {
			t.Fatalf("Failed to execute request: %v", err)
		}

		// Check response
		if resp.StatusCode != fiber.StatusInternalServerError {
			t.Errorf(
				"Expected status code %d, got %d",
				fiber.StatusInternalServerError,
				resp.StatusCode,
			)
		}

		// Parse response body
		respBody, _ := io.ReadAll(resp.Body)
		var response StdResponse[TestRequest]
		if err := sonic.Unmarshal(respBody, &response); err != nil {
			t.Errorf("Failed to unmarshal response: %v", err)
		}

		if response.Error == nil {
			t.Error("Expected error in response")
		}

		if *response.Error != "handler error" {
			t.Errorf("Expected error message 'handler error', got '%s'", *response.Error)
		}
	})

	t.Run("registers route with correct type name", func(t *testing.T) {
		server := createTestServerWithoutMiddleware()

		// Register a test handler
		ServeRoute(server, func(c *fiber.Ctx, req TestRequest) (TestRequest, error) {
			return req, nil
		})

		// Check that the route was registered with the correct path
		// We can test this by verifying the route exists
		testReq := TestRequest{Name: "test", Value: 1}
		body, _ := sonic.Marshal(testReq)

		req := httptest.NewRequest("POST", "/TestRequest", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")

		resp, err := server.App.Test(req)
		if err != nil {
			t.Fatalf("Failed to execute request: %v", err)
		}

		// If we get here without a 404, the route was registered correctly
		if resp.StatusCode == fiber.StatusNotFound {
			t.Error("Route was not registered correctly - got 404")
		}
	})
}

func TestServerStart(t *testing.T) {
	t.Run("start method uses correct port", func(t *testing.T) {
		// This test is tricky because Start() calls log.Fatal which would exit the test
		// We can't easily test the actual listening behavior in a unit test
		// But we can verify the port formatting logic by testing the configuration

		config := &ServerConfig{
			Host:      "localhost",
			Port:      9999,
			BodyLimit: DefaultBodyLimit,
		}

		server := NewServer(config)

		// Verify the port is set correctly in the config
		expectedPort := 9999
		if server.config.Port != expectedPort {
			t.Errorf("Expected port %d, got %d", expectedPort, server.config.Port)
		}

		// We can't test the actual Start() method easily because it calls log.Fatal()
		// which would terminate the test process. In a real application, you might
		// want to refactor Start() to be more testable by accepting a context or
		// returning an error instead of calling log.Fatal().
	})
}

// Benchmark tests
func BenchmarkNewServer(b *testing.B) {
	config := &ServerConfig{
		Host:      "localhost",
		Port:      8080,
		BodyLimit: DefaultBodyLimit,
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		NewServer(config)
	}
}

func BenchmarkServeRoute(b *testing.B) {
	server := NewServer(&ServerConfig{
		Host:      "localhost",
		Port:      8080,
		BodyLimit: DefaultBodyLimit,
	})

	ServeRoute(server, func(c *fiber.Ctx, req TestRequest) (TestRequest, error) {
		return req, nil
	})

	testReq := TestRequest{
		Name:  "benchmark",
		Value: 42,
	}
	body, _ := sonic.Marshal(testReq)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest("POST", "/TestRequest", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		server.App.Test(req)
	}
}
