package chain

import (
	"fmt"
	"net/http"
	"os"
	"strconv"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/stretchr/testify/suite"
)

// KamiClientTestSuite provides a test suite for KamiClient integration tests
type KamiClientTestSuite struct {
	suite.Suite
	client        *KamiChainRepo
	originalEnvs  map[string]string
	testNetuid    int
	kamiAvailable bool
}

// SetupSuite runs once before all tests in the suite
func (suite *KamiClientTestSuite) SetupSuite() {
	log.Info().Msg("=== Starting KamiClient Test Suite Setup ===")

	// Configure logging for tests
	zerolog.SetGlobalLevel(zerolog.InfoLevel)
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})
	log.Info().Msg("configured logging for test suite")

	// Store original environment variables
	log.Debug().Msg("storing original environment variables")
	suite.originalEnvs = make(map[string]string)
	envVars := []string{"KAMI_HOST", "KAMI_PORT", "NETUID", "TEST_NETUID"}
	for _, env := range envVars {
		if val := os.Getenv(env); val != "" {
			suite.originalEnvs[env] = val
			log.Debug().
				Str("env_var", env).
				Str("value", val).
				Msg("stored original environment variable")
		}
	}

	// Set test environment variables
	log.Debug().Msg("setting up test environment")
	suite.setupTestEnvironment()

	// Initialize KamiClient
	log.Info().Msg("initializing kami client for tests")
	client, err := NewKamiChainRepo()
	suite.Require().NoError(err, "Failed to create KamiClient")
	suite.client = client
	log.Info().Str("base_url", client.baseURL).Msg("kami client initialized successfully")

	// Parse test netuid
	suite.testNetuid = 98 // Default
	if netuidStr := os.Getenv("TEST_NETUID"); netuidStr != "" {
		if parsed, err := strconv.Atoi(netuidStr); err == nil {
			suite.testNetuid = parsed
			log.Debug().Int("test_netuid", parsed).Msg("using configured test netuid")
		} else {
			log.Warn().Str("test_netuid_str", netuidStr).Msg("failed to parse TEST_NETUID, using default")
		}
	} else {
		log.Debug().Int("test_netuid", suite.testNetuid).Msg("using default test netuid")
	}

	// Check if Kami server is available
	log.Info().Msg("checking kami server availability")
	suite.kamiAvailable = suite.checkKamiAvailability()
	if suite.kamiAvailable {
		log.Info().
			Str("base_url", suite.client.baseURL).
			Msg("✅ Kami server is available for testing")
	} else {
		log.Warn().Str("base_url", suite.client.baseURL).Msg("⚠️  Kami server not available - tests will be skipped")
	}

	log.Info().Msg("=== KamiClient Test Suite Setup Complete ===")
}

// TearDownSuite runs once after all tests in the suite
func (suite *KamiClientTestSuite) TearDownSuite() {
	// Restore original environment variables
	for env, val := range suite.originalEnvs {
		os.Setenv(env, val)
	}
	// Clear test-only environment variables
	testOnlyEnvs := []string{"TEST_NETUID"}
	for _, env := range testOnlyEnvs {
		if _, exists := suite.originalEnvs[env]; !exists {
			os.Unsetenv(env)
		}
	}
}

// setupTestEnvironment configures the test environment variables
func (suite *KamiClientTestSuite) setupTestEnvironment() {
	testConfig := map[string]string{
		"KAMI_HOST":   "localhost",
		"KAMI_PORT":   "3000",
		"TEST_NETUID": "98",
		"NETUID":      "98",
	}

	log.Debug().Msg("configuring test environment variables")
	for key, value := range testConfig {
		// Only set if not already defined
		if os.Getenv(key) == "" {
			os.Setenv(key, value)
			log.Debug().Str("env_var", key).Str("value", value).Msg("set test environment variable")
		} else {
			existingValue := os.Getenv(key)
			log.Debug().Str("env_var", key).Str("existing_value", existingValue).Msg("using existing environment variable")
		}
	}
	log.Debug().Msg("test environment configuration complete")
}

// checkKamiAvailability checks if the Kami server is running and accessible
func (suite *KamiClientTestSuite) checkKamiAvailability() bool {
	log.Debug().Msg("checking kami server availability")

	client := &http.Client{Timeout: 5 * time.Second}
	url := suite.client.baseURL + "/chain/latest-block"

	log.Debug().Str("health_check_url", url).Msg("making health check request")
	resp, err := client.Get(url)
	if err != nil {
		log.Debug().Err(err).Str("url", url).Msg("health check failed")
		return false
	}
	defer resp.Body.Close()

	isAvailable := resp.StatusCode == http.StatusOK
	log.Debug().
		Str("url", url).
		Int("status_code", resp.StatusCode).
		Bool("available", isAvailable).
		Msg("health check completed")

	return isAvailable
}

// skipIfKamiNotAvailable skips the test if Kami server is not available
func (suite *KamiClientTestSuite) skipIfKamiNotAvailable() {
	if !suite.kamiAvailable {
		log.Warn().
			Str("base_url", suite.client.baseURL).
			Msg("skipping test - kami server not available")
		suite.T().Skipf("⏭️  Skipping test: Kami server not available at %s", suite.client.baseURL)
	} else {
		log.Debug().Str("base_url", suite.client.baseURL).Msg("kami server available - proceeding with test")
	}
}

// TestKamiClientCreation tests the client creation with different configurations
func (suite *KamiClientTestSuite) TestKamiClientCreation() {
	suite.T().Run("default_configuration", func(t *testing.T) {
		// Temporarily clear environment variables
		os.Unsetenv("KAMI_HOST")
		os.Unsetenv("KAMI_PORT")
		defer func() {
			os.Setenv("KAMI_HOST", "localhost")
			os.Setenv("KAMI_PORT", "3000")
		}()

		client, err := NewKamiChainRepo()
		require.NoError(t, err)
		assert.Equal(t, "http://localhost:3000", client.baseURL)
	})

	suite.T().Run("custom_configuration", func(t *testing.T) {
		// Set custom environment variables
		os.Setenv("KAMI_HOST", "127.0.0.1")
		os.Setenv("KAMI_PORT", "8080")
		defer func() {
			os.Setenv("KAMI_HOST", "localhost")
			os.Setenv("KAMI_PORT", "3000")
		}()

		client, err := NewKamiChainRepo()
		require.NoError(t, err)
		assert.Equal(t, "http://127.0.0.1:8080", client.baseURL)
	})

	suite.T().Run("client_configuration", func(t *testing.T) {
		assert.NotNil(t, suite.client.httpClient)
		assert.Equal(t, 5, suite.client.httpClient.RetryMax)
		assert.Equal(t, 30*time.Second, suite.client.httpClient.HTTPClient.Timeout)
		assert.Equal(t, 500*time.Millisecond, suite.client.httpClient.RetryWaitMin)
		assert.Equal(t, 20*time.Second, suite.client.httpClient.RetryWaitMax)
	})
}

// TestGetLatestBlock tests the GetLatestBlock endpoint
func (suite *KamiClientTestSuite) TestGetLatestBlock() {
	suite.skipIfKamiNotAvailable()

	suite.T().Run("successful_fetch", func(t *testing.T) {
		// Create initial state
		initialState := &ChainState{block: 0, netuid: suite.testNetuid}

		// Get the function and call it
		updateFunc := suite.client.GetLatestBlock()
		updatedState, err := updateFunc(initialState)

		require.NoError(t, err)
		require.NotNil(t, updatedState)

		// Validate block data using thread-safe method
		assert.Greater(t, updatedState.GetBlock(), 0, "Block number should be positive")

		log.Info().
			Int("block_number", updatedState.GetBlock()).
			Msg("✅ latest block test validation successful")
		t.Logf("✅ Latest block: %d", updatedState.GetBlock())
	})

	suite.T().Run("multiple_calls_consistency", func(t *testing.T) {
		// Make multiple calls and ensure block number is non-decreasing
		var lastBlockNumber int
		initialState := &ChainState{block: 0}

		for i := 0; i < 3; i++ {
			updateFunc := suite.client.GetLatestBlock()
			updatedState, err := updateFunc(initialState)
			require.NoError(t, err)

			currentBlock := updatedState.GetBlock()
			if i > 0 {
				assert.GreaterOrEqual(t, currentBlock, lastBlockNumber,
					"Block number should not decrease between calls")
			}
			lastBlockNumber = currentBlock

			// Small delay between calls to allow for potential block progression
			time.Sleep(100 * time.Millisecond)
		}
	})
}

// TestGetSubnetMetagraph tests the GetSubnetMetagraph endpoint
func (suite *KamiClientTestSuite) TestGetSubnetMetagraph() {
	suite.skipIfKamiNotAvailable()

	suite.T().Run("successful_fetch", func(t *testing.T) {
		// Create initial state
		initialState := &ChainState{block: 0, netuid: suite.testNetuid}

		// Get the function and call it
		updateFunc := suite.client.GetSubnetMetagraph(suite.testNetuid)
		updatedState, err := updateFunc(initialState)

		require.NoError(t, err)
		require.NotNil(t, updatedState)

		// Validate metagraph data using thread-safe method
		metagraph := updatedState.GetMetagraph()
		assert.Equal(t, suite.testNetuid, metagraph.Netuid)
		assert.NotEmpty(t, metagraph.OwnerHotkey, "Owner hotkey should not be empty")
		assert.NotEmpty(t, metagraph.OwnerColdkey, "Owner coldkey should not be empty")
		assert.Greater(t, metagraph.Block, 0, "Block should be positive")
		assert.Greater(t, metagraph.Tempo, 0, "Tempo should be positive")
		assert.GreaterOrEqual(t, metagraph.MaxUids, 0, "MaxUids should be non-negative")
		assert.GreaterOrEqual(t, metagraph.NumUids, 0, "NumUids should be non-negative")
		assert.LessOrEqual(
			t,
			metagraph.NumUids,
			metagraph.MaxUids,
			"NumUids should not exceed MaxUids",
		)

		// Validate difficulty fields (can be numbers or hex strings)
		assert.True(
			t,
			metagraph.Difficulty.BigInt().Sign() >= 0,
			"Difficulty should be non-negative",
		)
		assert.True(
			t,
			metagraph.MinDifficulty.BigInt().Sign() >= 0,
			"MinDifficulty should be non-negative",
		)
		assert.True(
			t,
			metagraph.MaxDifficulty.BigInt().Sign() >= 0,
			"MaxDifficulty should be non-negative",
		)

		// Validate array consistency
		if metagraph.NumUids > 0 {
			assert.Len(t, metagraph.Hotkeys, metagraph.NumUids, "Hotkeys length mismatch")
			assert.Len(t, metagraph.Coldkeys, metagraph.NumUids, "Coldkeys length mismatch")
			assert.Len(t, metagraph.Active, metagraph.NumUids, "Active length mismatch")
			assert.Len(
				t,
				metagraph.ValidatorPermit,
				metagraph.NumUids,
				"ValidatorPermit length mismatch",
			)
		}

		log.Info().
			Int("netuid", metagraph.Netuid).
			Int("num_uids", metagraph.NumUids).
			Int("max_uids", metagraph.MaxUids).
			Int("block", metagraph.Block).
			Int("tempo", metagraph.Tempo).
			Str("owner_hotkey", metagraph.OwnerHotkey).
			Str("difficulty", metagraph.Difficulty.String()).
			Msg("✅ subnet metagraph test validation successful")
		t.Logf("✅ Subnet %d metadata:", metagraph.Netuid)
		t.Logf("   UIDs: %d/%d", metagraph.NumUids, metagraph.MaxUids)
		t.Logf("   Block: %d, Tempo: %d", metagraph.Block, metagraph.Tempo)
		t.Logf(
			"   Difficulty: %s (Min: %s, Max: %s)",
			metagraph.Difficulty.String(),
			metagraph.MinDifficulty.String(),
			metagraph.MaxDifficulty.String(),
		)
		t.Logf("   Owner: %s", metagraph.OwnerHotkey)
		if len(metagraph.Name) > 0 {
			t.Logf("   Name: %v", metagraph.Name)
		}
	})

	suite.T().Run("invalid_netuid", func(t *testing.T) {
		invalidNetuid := 99999
		initialState := &ChainState{block: 0}

		updateFunc := suite.client.GetSubnetMetagraph(invalidNetuid)
		_, err := updateFunc(initialState)

		// Should return an error for invalid netuid
		if err != nil {
			t.Logf("✅ Expected error for invalid netuid %d: %v", invalidNetuid, err)
		} else {
			t.Errorf("❌ Expected error for invalid netuid %d, got success", invalidNetuid)
		}
	})
}

// TestGetKeyringPairInfo tests the GetKeyringPairInfo endpoint
func (suite *KamiClientTestSuite) TestGetKeyringPairInfo() {
	suite.skipIfKamiNotAvailable()

	suite.T().Run("successful_fetch", func(t *testing.T) {
		// Create initial state
		initialState := &ChainState{block: 0, netuid: suite.testNetuid}

		// Get the function and call it
		updateFunc := suite.client.GetKeyringPairInfo()
		updatedState, err := updateFunc(initialState)

		require.NoError(t, err)
		require.NotNil(t, updatedState)

		// For this test, we just verify that the function runs without error
		// since GetKeyringPairInfo doesn't modify the ChainState in our current implementation
		log.Info().Msg("✅ keyring pair info test validation successful")
		t.Logf("✅ Keyring pair info function executed successfully")
	})
}

// TestConcurrentRequests tests concurrent access to ensure thread safety
func (suite *KamiClientTestSuite) TestConcurrentRequests() {
	suite.skipIfKamiNotAvailable()

	suite.T().Run("concurrent_latest_block", func(t *testing.T) {
		const numGoroutines = 10
		results := make(chan error, numGoroutines)

		start := time.Now()

		for i := 0; i < numGoroutines; i++ {
			go func(id int) {
				initialState := &ChainState{block: 0}
				updateFunc := suite.client.GetLatestBlock()
				_, err := updateFunc(initialState)
				if err != nil {
					results <- fmt.Errorf("goroutine %d failed: %w", id, err)
					return
				}
				results <- nil
			}(i)
		}

		// Collect results
		for i := 0; i < numGoroutines; i++ {
			select {
			case err := <-results:
				assert.NoError(t, err)
			case <-time.After(30 * time.Second):
				t.Fatalf("Timeout waiting for concurrent request %d", i)
			}
		}

		duration := time.Since(start)
		log.Info().
			Int("num_goroutines", numGoroutines).
			Dur("total_duration", duration).
			Dur("avg_duration_per_request", duration/time.Duration(numGoroutines)).
			Msg("✅ concurrent requests test completed successfully")
		t.Logf("✅ %d concurrent requests completed in %v", numGoroutines, duration)
	})

	suite.T().Run("mixed_concurrent_requests", func(t *testing.T) {
		const numGoroutines = 6
		results := make(chan error, numGoroutines)

		// Mix of different endpoint calls
		endpoints := []func() error{
			func() error {
				initialState := &ChainState{block: 0}
				updateFunc := suite.client.GetLatestBlock()
				_, err := updateFunc(initialState)
				return err
			},
			func() error {
				initialState := &ChainState{block: 0}
				updateFunc := suite.client.GetSubnetMetagraph(suite.testNetuid)
				_, err := updateFunc(initialState)
				return err
			},
			func() error {
				initialState := &ChainState{block: 0}
				updateFunc := suite.client.GetKeyringPairInfo()
				_, err := updateFunc(initialState)
				return err
			},
		}

		for i := 0; i < numGoroutines; i++ {
			go func(id int) {
				endpoint := endpoints[id%len(endpoints)]
				err := endpoint()
				if err != nil {
					results <- fmt.Errorf("goroutine %d failed: %w", id, err)
				} else {
					results <- nil
				}
			}(i)
		}

		// Collect results
		for i := 0; i < numGoroutines; i++ {
			select {
			case err := <-results:
				assert.NoError(t, err)
			case <-time.After(30 * time.Second):
				t.Fatalf("Timeout waiting for mixed concurrent request %d", i)
			}
		}

		log.Info().
			Int("num_goroutines", numGoroutines).
			Int("num_endpoints", len(endpoints)).
			Msg("✅ mixed concurrent requests test completed successfully")
		t.Logf("✅ Mixed concurrent requests completed successfully")
	})
}

// TestErrorHandling tests error handling scenarios
func (suite *KamiClientTestSuite) TestErrorHandling() {
	suite.T().Run("invalid_server", func(t *testing.T) {
		// Create client with invalid server
		originalHost := os.Getenv("KAMI_HOST")
		originalPort := os.Getenv("KAMI_PORT")

		os.Setenv("KAMI_HOST", "invalid-host")
		os.Setenv("KAMI_PORT", "99999")

		defer func() {
			os.Setenv("KAMI_HOST", originalHost)
			os.Setenv("KAMI_PORT", originalPort)
		}()

		invalidClient, err := NewKamiChainRepo()
		require.NoError(t, err)

		// All requests should fail
		initialState := &ChainState{block: 0}

		updateFunc1 := invalidClient.GetLatestBlock()
		_, err = updateFunc1(initialState)
		assert.Error(t, err, "Should fail with invalid server")

		updateFunc2 := invalidClient.GetSubnetMetagraph(suite.testNetuid)
		_, err = updateFunc2(initialState)
		assert.Error(t, err, "Should fail with invalid server")

		updateFunc3 := invalidClient.GetKeyringPairInfo()
		_, err = updateFunc3(initialState)
		assert.Error(t, err, "Should fail with invalid server")

		log.Info().Msg("✅ error handling test completed successfully")
		t.Logf("✅ Error handling works correctly for invalid server")
	})
}

// BenchmarkKamiClientOperations benchmarks the main operations
func (suite *KamiClientTestSuite) TestBenchmarkOperations() {
	if !suite.kamiAvailable {
		suite.T().Skip("Kami server not available for benchmarks")
	}

	suite.T().Run("benchmark_latest_block", func(t *testing.T) {
		const iterations = 10
		start := time.Now()

		for i := 0; i < iterations; i++ {
			initialState := &ChainState{block: 0}
			updateFunc := suite.client.GetLatestBlock()
			_, err := updateFunc(initialState)
			require.NoError(t, err)
		}

		duration := time.Since(start)
		avgTime := duration / iterations

		log.Info().
			Int("iterations", iterations).
			Dur("total_duration", duration).
			Dur("avg_duration", avgTime).
			Msg("✅ GetLatestBlock benchmark completed")
		t.Logf("✅ GetLatestBlock: %d iterations in %v (avg: %v per request)",
			iterations, duration, avgTime)
	})

	suite.T().Run("benchmark_subnet_metagraph", func(t *testing.T) {
		const iterations = 5 // Fewer iterations as this is a heavier operation
		start := time.Now()

		for i := 0; i < iterations; i++ {
			initialState := &ChainState{block: 0}
			updateFunc := suite.client.GetSubnetMetagraph(suite.testNetuid)
			_, err := updateFunc(initialState)
			require.NoError(t, err)
		}

		duration := time.Since(start)
		avgTime := duration / iterations

		log.Info().
			Int("iterations", iterations).
			Dur("total_duration", duration).
			Dur("avg_duration", avgTime).
			Msg("✅ GetSubnetMetagraph benchmark completed")
		t.Logf("✅ GetSubnetMetagraph: %d iterations in %v (avg: %v per request)",
			iterations, duration, avgTime)
	})
}

// TestKamiClient runs all tests - both unit and integration
func TestKamiClient(t *testing.T) {
	suite.Run(t, new(KamiClientTestSuite))
}

// TestClientCreation tests client creation without requiring Kami server
func TestClientCreation(t *testing.T) {
	client, err := NewKamiChainRepo()
	require.NoError(t, err)
	require.NotNil(t, client)
	assert.NotEmpty(t, client.baseURL)
	assert.NotNil(t, client.httpClient)
}

// TestEnvironmentVariables tests environment variable handling
func TestEnvironmentVariables(t *testing.T) {
	tests := []struct {
		name     string
		host     string
		port     string
		expected string
	}{
		{"default", "", "", "http://localhost:3000"},
		{"custom_host", "127.0.0.1", "", "http://127.0.0.1:3000"},
		{"custom_port", "", "8080", "http://localhost:8080"},
		{"custom_both", "192.168.1.100", "9000", "http://192.168.1.100:9000"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Store original values
			originalHost := os.Getenv("KAMI_HOST")
			originalPort := os.Getenv("KAMI_PORT")

			// Set test values
			if tt.host != "" {
				os.Setenv("KAMI_HOST", tt.host)
			} else {
				os.Unsetenv("KAMI_HOST")
			}

			if tt.port != "" {
				os.Setenv("KAMI_PORT", tt.port)
			} else {
				os.Unsetenv("KAMI_PORT")
			}

			// Restore after test
			defer func() {
				if originalHost != "" {
					os.Setenv("KAMI_HOST", originalHost)
				} else {
					os.Unsetenv("KAMI_HOST")
				}
				if originalPort != "" {
					os.Setenv("KAMI_PORT", originalPort)
				} else {
					os.Unsetenv("KAMI_PORT")
				}
			}()

			client, err := NewKamiChainRepo()
			require.NoError(t, err)
			assert.Equal(t, tt.expected, client.baseURL)
		})
	}
}
