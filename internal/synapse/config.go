package synapse

// // NewConfigFromEnv loads synapse configuration from environment using
// // the shared pkg/config env structs. It returns a Config populated with
// // sensible defaults when env vars are missing.
// func NewConfigFromEnv(ctx context.Context) (Config, error) {
// 	var clientEnv pkgconfig.ClientEnvConfig
// 	if err := envconfig.Process(ctx, &clientEnv); err != nil {
// 		return Config{}, fmt.Errorf("process client env: %w", err)
// 	}
//
// 	var serverEnv pkgconfig.ServerEnvConfig
// 	// Server env vars are optional; ignore error if not present
// 	_ = envconfig.Process(ctx, &serverEnv)
//
// 	port := 0
// 	if serverEnv.Port != 0 {
// 		port = serverEnv.Port
// 	}
// 	address := ":8080"
// 	if port != 0 {
// 		address = ":" + strconv.Itoa(port)
// 	}
//
// 	timeout := 30 * time.Second
// 	if clientEnv.ClientTimeout != 0 {
// 		timeout = time.Duration(clientEnv.ClientTimeout) * time.Second
// 	}
//
// 	return Config{
// 		Address:       address,
// 		ClientTimeout: timeout,
// 		RetryMax:      3,
// 		RetryWait:     500 * time.Millisecond,
// 	}, nil
// }
