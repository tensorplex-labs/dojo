package scoring

import (
	"gonum.org/v1/gonum/floats"
	"gonum.org/v1/gonum/mat"
)

func MinMaxScale(scores []float64) []float64 {
	result := make([]float64, len(scores))
	copy(result, scores)

	min := floats.Min(result)
	max := floats.Max(result)

	if max != min {
		floats.AddConst(-min, result)
		floats.Scale(1.0/(max-min), result)
	} else {
		floats.Scale(0, result)
	}

	return result
}

func MinMaxScaleOnMatrix(scores *mat.Dense) *mat.Dense {
	rows, cols := scores.Dims()

	minMaxScaledScores := mat.NewDense(rows, cols, nil)

	for rowIdx := range rows {
		rowScores := mat.Row(nil, rowIdx, scores)
		minMaxScaledRowScores := MinMaxScale(rowScores)
		minMaxScaledScores.SetRow(rowIdx, minMaxScaledRowScores)
	}

	return minMaxScaledScores
}
