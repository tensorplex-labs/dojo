package scheduler

import (
	"reflect"
	"runtime"
	"strings"

	"github.com/rs/zerolog/log"
)

func InferNameFromFunc(f any) string {
	v := reflect.ValueOf(f)
	if v.Kind() != reflect.Func {
		log.Warn().Msgf("Expected a function, got: %s", v.Kind())
		return "unknown"
	}

	funcPtr := runtime.FuncForPC(v.Pointer())
	if funcPtr == nil {
		log.Warn().Msgf("Could not retrieve function pointer for: %s", v.Type().String())
		return "unknown"
	}

	fullName := funcPtr.Name()
	parts := strings.Split(fullName, ".")
	// Just return the last part
	return parts[len(parts)-1]
}
