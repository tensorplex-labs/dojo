package chainutils

import (
	"os"
)

func CheckIfMiner(alphaStake float64, rootStake float64) (bool, error) {
	if alphaStake <= 0 || rootStake <= 0 {
		return false, nil
	}

	effectiveRootStake := rootStake * 0.18

	effectiveStake := alphaStake + effectiveRootStake
	var stakeFilter float64
	if os.Getenv("ENVIRONMENT") == "test" {
		stakeFilter = 1000 // Test environment threshold
	} else {
		stakeFilter = 10000 // Production environment threshold
	}

	if effectiveStake < stakeFilter {
		return true, nil
	}
	return false, nil
}
