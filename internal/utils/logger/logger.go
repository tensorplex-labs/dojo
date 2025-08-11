package logger

import (
	"flag"
	"os"

	"go.uber.org/zap"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/rs/zerolog/pkgerrors"
)

var Logger *zap.Logger

func initLogger() {
	err := godotenv.Load()
	if err != nil {
		log.Fatal().Msg("Error loading .env file!")
	}

	zerolog.ErrorStackMarshaler = pkgerrors.MarshalStack
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr}).With().Caller().Logger()

	debug := flag.Bool("debug", false, "sets log level to debug")
	trace := flag.Bool("trace", false, "sets log level to trace")
	info := flag.Bool("info", false, "sets log level to info (default)")
	flag.Parse()

	// Set default to Info level
	logLevel := zerolog.InfoLevel
	
	if *debug {
		logLevel = zerolog.DebugLevel
	} else if *trace {
		logLevel = zerolog.TraceLevel
	} else if *info {
		logLevel = zerolog.InfoLevel
	}
	
	// Apply the log level globally
	zerolog.SetGlobalLevel(logLevel)
	
	// Log the current level
	switch logLevel {
	case zerolog.DebugLevel:
		log.Debug().Msg("Debug mode enabled")
	case zerolog.TraceLevel:
		log.Trace().Msg("Trace mode enabled")
	case zerolog.InfoLevel:
		log.Info().Msg("Info mode enabled")
	}
}

// Init initializes the logger with the configuration from the environment
// and command line flags.
// It sets up the global logger to use zerolog with console output.
// Example usage:
//
//	logger.Init() <- inside whichever main() function in your entrypoint
//
// Then, `go run cmd/validator.main.go --debug`
func Init() {
	initLogger()
}

// Sugar returns a sugared logger for easier use
// TODO: replace with zerolog
func Sugar() *zap.SugaredLogger {
	return Logger.Sugar()
}
