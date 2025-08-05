package scoring

import (
	"gonum.org/v1/gonum/floats"
)

func TransformToRange01(arr []float64) []float64 {
	result := make([]float64, len(arr))
	copy(result, arr)

	floats.AddConst(1, result)
	floats.Scale(0.5, result)

	return result
}
