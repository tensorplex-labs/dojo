// Package chainutils/check_stake.go contains stake checking logic
package chainutils

const stakeFilter = 10000

func CheckIfMiner(alphaStake, rootStake float64) (bool, error) {
	effectiveRootStake := rootStake * 0.18

	effectiveStake := alphaStake + effectiveRootStake

	return effectiveStake < stakeFilter, nil
}
