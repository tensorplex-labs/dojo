package synapse

// func LoadConfigFromEnv() Config {
// 	addr := os.Getenv("SYNAPSE_ADDR")
// 	if addr == "" {
// 		addr = "0.0.0.0:8080"
// 	}
// 	clientTimeout := 5 * time.Second
// 	if v := os.Getenv("SYNAPSE_CLIENT_TIMEOUT"); v != "" {
// 		if t, err := time.ParseDuration(v); err == nil {
// 			clientTimeout = t
// 		}
// 	}
// 	retryMax := 3
// 	if v := os.Getenv("SYNAPSE_RETRY_MAX"); v != "" {
// 		if i, err := strconv.Atoi(v); err == nil {
// 			retryMax = i
// 		}
// 	}
// 	retryWait := 500 * time.Millisecond
// 	if v := os.Getenv("SYNAPSE_RETRY_WAIT"); v != "" {
// 		if t, err := time.ParseDuration(v); err == nil {
// 			retryWait = t
// 		}
// 	}
// 	return Config{Address: addr, ClientTimeout: clientTimeout, RetryMax: retryMax, RetryWait: retryWait}
// }
