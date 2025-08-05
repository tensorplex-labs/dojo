package config

type ChainEnvConfig struct {
	Netuid int `env:"NETUID"`
}

type WalletEnvConfig struct {
	WalletHotkey   string `env:"WALLET_HOTKEY"`
	WalltetColdkey string `env:"WALLET_COLDKEY"`
	BittensorDir   string `env:"BITTENSOR_DIR"`
}

type KamiEnvConfig struct {
	WalletEnvConfig
	SubtensorNetwork string `env:"SUBTENSOR_NETWORK"`
	KamiHost         string `env:"KAMI_HOST"`
	KamiPort         string `env:"KAMI_PORT"`
}

type ServerEnvConfig struct {
	ServerPort    int `env:"SERVER_PORT"`
	BodySizeLimit int `env:"SERVER_BODY_LIMIT"`
}

type ClientEnvConfig struct {
	ClientTimeout int `env:"CLIENT_TIMEOUT"`
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
