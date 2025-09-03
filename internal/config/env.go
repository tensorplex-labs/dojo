// Package config defines environment configuration structs and loaders.
package config

import "time"

// ChainEnvConfig holds chain-specific environment values.
type ChainEnvConfig struct {
	Netuid int `env:"NETUID,default=0"`
}

// WalletEnvConfig holds wallet key configuration.
type WalletEnvConfig struct {
	WalletHotkey   string `env:"WALLET_HOTKEY,default="`
	WalltetColdkey string `env:"WALLET_COLDKEY,default="`
	BittensorDir   string `env:"BITTENSOR_DIR,default="`
}

// KamiEnvConfig contains Kami service target and keys.
type KamiEnvConfig struct {
	WalletEnvConfig
	SubtensorNetwork string `env:"SUBTENSOR_NETWORK,default=local"`
	KamiHost         string `env:"KAMI_HOST,default=127.0.0.1"`
	KamiPort         string `env:"KAMI_PORT,default=8080"`
}

// ServerEnvConfig configures the server.
type ServerEnvConfig struct {
	Address       string `env:"AXON_IP,default=127.0.0.1"`
	Port          int    `env:"AXON_PORT,default=8080"`
	BodySizeLimit int    `env:"SERVER_BODY_LIMIT,default=1048576"`
}

// ClientEnvConfig configures the client.
type ClientEnvConfig struct {
	ClientTimeout time.Duration `env:"CLIENT_TIMEOUT,default=30s"`
}

// RedisEnvConfig configures Redis connection.
type RedisEnvConfig struct {
	RedisHost     string `env:"REDIS_HOST,default=127.0.0.1"`
	RedisPort     int    `env:"REDIS_PORT,default=6379"`
	RedisPassword string `env:"REDIS_PASSWORD,default="`
	RedisDB       int    `env:"REDIS_DB,default=0"`
}

// SyntheticApiEnvConfig configures synthetic API access.
type SyntheticApiEnvConfig struct {
	OpenrouterApiKey string `env:"OPENROUTER_API_KEY,default="` //nolint:staticcheck
	SyntheticApiUrl  string `env:"SYNTHETIC_API_URL,default=localhost:5003"` //nolint:staticcheck
}

// TaskApiEnvConfig configures task API access.
type TaskApiEnvConfig struct {
	TaskApiUrl string `env:"TASK_API_URL,default=localhost:5004"` //nolint:staticcheck
}

// MinerEnvConfig configures miner runtime.
type MinerEnvConfig struct {
	ChainEnvConfig
	WalletEnvConfig
	ServerEnvConfig
}

// ValidatorEnvConfig configures validator runtime.
type ValidatorEnvConfig struct {
	ChainEnvConfig
	ClientEnvConfig
	Environment string `env:"ENVIRONMENT,default=dev"`
}
