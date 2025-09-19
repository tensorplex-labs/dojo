// Package chainutils/check_stake.go contains stake checking logic
package chainutils

import (
	"os"
)

func CheckIfMiner(alphaStake, rootStake float64) (bool, error) {
	effectiveRootStake := rootStake * 0.18

	effectiveStake := alphaStake + effectiveRootStake
	var stakeFilter float64
	if os.Getenv("ENVIRONMENT") != "prod" {
		stakeFilter = 1000 // dev/test environment threshold
	} else {
		stakeFilter = 10000 // Production environment threshold
	}

	return effectiveStake < stakeFilter, nil
}
