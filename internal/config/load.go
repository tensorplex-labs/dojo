package config

import (
	"os"
	"strconv"
	"time"
)

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func atoiWithDefault(s string, def int) int {
	if s == "" {
		return def
	}
	i, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return i
}

func durationWithDefault(s string, def time.Duration) time.Duration {
	if s == "" {
		return def
	}
	d, err := time.ParseDuration(s)
	if err != nil {
		// try seconds as int
		if i, err2 := strconv.Atoi(s); err2 == nil {
			return time.Duration(i) * time.Second
		}
		return def
	}
	return d
}

func LoadKamiEnv() (*KamiEnvConfig, error) {
	cfg := &KamiEnvConfig{
		SubtensorNetwork: getenv("SUBTENSOR_NETWORK", "local"),
		KamiHost:         getenv("KAMI_HOST", "127.0.0.1"),
		KamiPort:         getenv("KAMI_PORT", "8080"),
		WalletEnvConfig: WalletEnvConfig{
			WalletHotkey:   getenv("WALLET_HOTKEY", ""),
			WalltetColdkey: getenv("WALLET_COLDKEY", ""),
			BittensorDir:   getenv("BITTENSOR_DIR", ""),
		},
	}
	return cfg, nil
}

func LoadRedisEnv() (*RedisEnvConfig, error) {
	cfg := &RedisEnvConfig{
		RedisHost:     getenv("REDIS_HOST", "127.0.0.1"),
		RedisPort:     atoiWithDefault(getenv("REDIS_PORT", "6379"), 6379),
		RedisPassword: getenv("REDIS_PASSWORD", ""),
		RedisDB:       atoiWithDefault(getenv("REDIS_DB", "0"), 0),
	}
	return cfg, nil
}

func LoadValidatorEnv() (*ValidatorEnvConfig, error) {
	cfg := &ValidatorEnvConfig{
		ChainEnvConfig: ChainEnvConfig{
			Netuid: atoiWithDefault(getenv("NETUID", "0"), 0),
		},
		ClientEnvConfig: ClientEnvConfig{
			ClientTimeout: durationWithDefault(getenv("CLIENT_TIMEOUT", "30s"), 30*time.Second),
		},
	}
	return cfg, nil
}

func LoadSyntheticApiEnv() (*SyntheticApiEnvConfig, error) {
	cfg := &SyntheticApiEnvConfig{
		OpenrouterApiKey: getenv("OPENROUTER_API_KEY", ""),
		SyntheticApiUrl:  getenv("SYNTHETIC_API_URL", "localhost:5003"),
	}
	return cfg, nil
}
