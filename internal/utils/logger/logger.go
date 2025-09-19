// Package logger provides a global logger for the application
package logger

import (
	"flag"
	"os"
	"strings"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/rs/zerolog/pkgerrors"
	"go.uber.org/zap"
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

	environment := strings.ToLower(os.Getenv("ENVIRONMENT"))
	if environment == "" {
		environment = "prod"
	}

	// Set default to Info level
	var logLevel zerolog.Level
	switch environment {
	case "dev", "test":
		logLevel = zerolog.TraceLevel
		log.Info().Str("environment", environment).Msg("Development/Test environment detected - enabling all log levels")
	case "prod":
		logLevel = zerolog.InfoLevel
		log.Info().Str("environment", environment).Msg("Production environment detected - enabling info level and above")
	default:
		logLevel = zerolog.InfoLevel
		log.Warn().Str("environment", environment).Msg("Unknown environment - defaulting to production log level (info and above)")
	}

	if *debug {
		logLevel = zerolog.DebugLevel
		log.Info().Msg("Debug flag detected - overriding environment log level")
	} else if *trace {
		logLevel = zerolog.TraceLevel
		log.Info().Msg("Trace flag detected - overriding environment log level")
	} else if *info {
		logLevel = zerolog.InfoLevel
		log.Info().Msg("Info flag detected - overriding environment log level")
	}

	// Apply the log level globally
	zerolog.SetGlobalLevel(logLevel)

	// Log the current level
	switch logLevel {
	case zerolog.DebugLevel:
		log.Debug().Str("environment", environment).Msg("Debug logging enabled")
	case zerolog.TraceLevel:
		log.Trace().Str("environment", environment).Msg("Trace logging enabled")
	case zerolog.InfoLevel:
		log.Info().Str("environment", environment).Msg("Info logging enabled")
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
