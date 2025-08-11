package chainutils

func CheckEffectiveStake(alphaStake float64, rootStake float64) (bool, error) {
	if alphaStake <= 0 || rootStake <= 0 {
		return false, nil
	}

	effectiveRootStake := rootStake * 0.18

	effectiveStake := alphaStake + effectiveRootStake
	if effectiveStake < 10000 {
		return false, nil
	}
	return true, nil
}
