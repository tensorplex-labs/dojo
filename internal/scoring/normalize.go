package scoring

import (
	"gonum.org/v1/gonum/floats"
)

func L1Normalize(arr []float64) []float64 {
	result := make([]float64, len(arr))
	copy(result, arr)

	sum := floats.Sum(result)
	if sum > 0 {
		floats.Scale(1.0/sum, result)
	}

	return result
}
