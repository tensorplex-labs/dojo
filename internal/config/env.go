// Package config defines environment configuration structs and loaders.
package config

import (
	"strings"
	"time"

	"github.com/caarlos0/env/v11"
)

type AppConfig struct {
	ChainEnvConfig
	WalletEnvConfig
	KamiEnvConfig
	ServerEnvConfig
	ClientEnvConfig
	RedisEnvConfig
	SyntheticAPIEnvConfig
	TaskAPIEnvConfig
	ValidatorEnvConfig
}

func LoadConfig() (*AppConfig, error) {
	cfg := &AppConfig{}
	if err := env.Parse(cfg); err != nil {
		return nil, err
	}
	return cfg, nil
}

// ChainEnvConfig holds chain-specific environment values.
type ChainEnvConfig struct {
	Netuid int `env:"NETUID" envDefault:"98"`
}

// WalletEnvConfig holds wallet key configuration.
type WalletEnvConfig struct {
	WalletHotkey   string `env:"WALLET_HOTKEY"`
	WalltetColdkey string `env:"WALLET_COLDKEY"`
	BittensorDir   string `env:"BITTENSOR_DIR" envDefault:"~/.bittensor"`
}

// KamiEnvConfig contains Kami service target and keys.
type KamiEnvConfig struct {
	WalletEnvConfig
	SubtensorNetwork string `env:"SUBTENSOR_NETWORK" envDefault:"finney"`
	KamiHost         string `env:"KAMI_HOST" envDefault:"kami"`
	KamiPort         string `env:"KAMI_PORT" envDefault:"3000"`
}

// ServerEnvConfig configures the server.
type ServerEnvConfig struct {
	Address       string `env:"AXON_IP" envDefault:"127.0.0.1"`
	Port          int    `env:"AXON_PORT" envDefault:"8080"`
	BodySizeLimit int    `env:"SERVER_BODY_LIMIT" envDefault:"1048576"`
}

// ClientEnvConfig configures the client.
type ClientEnvConfig struct {
	ClientTimeout time.Duration `env:"CLIENT_TIMEOUT" envDefault:"30s"`
}

// RedisEnvConfig configures Redis connection.
type RedisEnvConfig struct {
	RedisHost     string `env:"REDIS_HOST" envDefault:"redis"`
	RedisPort     int    `env:"REDIS_PORT" envDefault:"6379"`
	RedisPassword string `env:"REDIS_PASSWORD" envDefault:"password"`
	RedisDB       int    `env:"REDIS_DB" envDefault:"0"`
	RedisUsername string `env:"REDIS_USERNAME" envDefault:"admin"`
}

// SyntheticAPIEnvConfig configures synthetic API access.
type SyntheticAPIEnvConfig struct {
	OpenrouterAPIKey string `env:"OPENROUTER_API_KEY"`
	SyntheticAPIUrl  string `env:"SYNTHETIC_API_URL" envDefault:"synthetic-gen:5003"`
}

// TaskAPIEnvConfig configures task API access.
type TaskAPIEnvConfig struct {
	TaskAPIUrl string `env:"TASK_API_URL" envDefault:"https://dojo.network/api/v1"`
}

// ValidatorEnvConfig configures validator runtime.
type ValidatorEnvConfig struct {
	ChainEnvConfig
	ClientEnvConfig
	Environment string `env:"ENVIRONMENT" envDefault:"prod"`
}

type IntervalConfig struct {
	MetagraphInterval     time.Duration
	TaskRoundInterval     time.Duration
	BlockInterval         time.Duration
	ScoringInterval       time.Duration
	ScoreResetInterval    time.Duration
	WeightSettingInterval time.Duration
	TaskExpiryDuration    time.Duration
	VotersCacheInterval   time.Duration
}

var (
	DevIntervalConfig = &IntervalConfig{
		MetagraphInterval:     5 * time.Second,
		TaskRoundInterval:     10 * time.Second,
		BlockInterval:         2 * time.Second,
		ScoringInterval:       5 * time.Minute,
		ScoreResetInterval:    1 * time.Hour,
		WeightSettingInterval: 30 * time.Minute,
		TaskExpiryDuration:    10 * time.Minute,
		VotersCacheInterval:   15 * time.Second,
	}
	TestIntervalConfig = &IntervalConfig{
		MetagraphInterval:     30 * time.Second,
		TaskRoundInterval:     15 * time.Minute,
		BlockInterval:         12 * time.Second,
		ScoringInterval:       5 * time.Minute,
		ScoreResetInterval:    24 * time.Hour,
		WeightSettingInterval: 1 * time.Hour,
		TaskExpiryDuration:    2 * time.Hour,
		VotersCacheInterval:   15 * time.Minute,
	}
	ProdIntervalConfig = &IntervalConfig{
		MetagraphInterval:     30 * time.Second,
		TaskRoundInterval:     3 * time.Hour,
		BlockInterval:         12 * time.Second,
		ScoringInterval:       15 * time.Minute,
		ScoreResetInterval:    24 * time.Hour,
		WeightSettingInterval: 1 * time.Hour,
		TaskExpiryDuration:    6 * time.Hour,
		VotersCacheInterval:   15 * time.Minute,
	}
)

func NewIntervalConfig(environment string) *IntervalConfig {
	switch strings.ToLower(environment) {
	case "dev":
		return DevIntervalConfig
	case "test":
		return TestIntervalConfig
	case "prod":
		return ProdIntervalConfig
	}

	return DevIntervalConfig
}
