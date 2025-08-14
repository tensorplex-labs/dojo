package config

import "time"

type ChainEnvConfig struct {
	Netuid int `env:"NETUID,default=0"`
}

type WalletEnvConfig struct {
	WalletHotkey   string `env:"WALLET_HOTKEY,default="`
	WalltetColdkey string `env:"WALLET_COLDKEY,default="`
	BittensorDir   string `env:"BITTENSOR_DIR,default="`
}

type KamiEnvConfig struct {
	WalletEnvConfig
	SubtensorNetwork string `env:"SUBTENSOR_NETWORK,default=local"`
	KamiHost         string `env:"KAMI_HOST,default=127.0.0.1"`
	KamiPort         string `env:"KAMI_PORT,default=8080"`
}

type ServerEnvConfig struct {
	Address       string `env:"AXON_IP,default=127.0.0.1"`
	Port          int    `env:"AXON_PORT,default=8080"`
	BodySizeLimit int    `env:"SERVER_BODY_LIMIT,default=1048576"`
}

type ClientEnvConfig struct {
	ClientTimeout time.Duration `env:"CLIENT_TIMEOUT,default=30s"`
}

type RedisEnvConfig struct {
	RedisHost     string `env:"REDIS_HOST,default=127.0.0.1"`
	RedisPort     int    `env:"REDIS_PORT,default=6379"`
	RedisPassword string `env:"REDIS_PASSWORD,default="`
	RedisDB       int    `env:"REDIS_DB,default=0"`
}

type SyntheticApiEnvConfig struct {
	OpenrouterApiKey string `env:"OPENROUTER_API_KEY,default="`
	SyntheticApiUrl  string `env:"SYNTHETIC_API_URL,default=localhost:5003"`
}

type MinerEnvConfig struct {
	ChainEnvConfig
	WalletEnvConfig
	ServerEnvConfig
}

type ValidatorEnvConfig struct {
	ChainEnvConfig
	ClientEnvConfig
}
