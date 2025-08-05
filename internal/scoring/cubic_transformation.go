package scoring

import "math"

func ApplyCubicTransformation(normalizedScores []float64, scaling, translation, offset float64) []float64 {
	rows := len(normalizedScores)

	cubicTransformedScores := make([]float64, rows)

	for rowIdx := range rows {
		normalizedScore := normalizedScores[rowIdx]

		diff := normalizedScore - translation

		cubicReward := scaling*diff*diff*diff + offset

		if math.IsNaN(cubicReward) {
			cubicReward = 0.0
		}

		cubicTransformedScores[rowIdx] = cubicReward
	}

	return cubicTransformedScores
}
