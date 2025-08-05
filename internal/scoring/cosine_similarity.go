package scoring

import (
	"math"

	"gonum.org/v1/gonum/floats"
	"gonum.org/v1/gonum/mat"
)

func CalculateCosineSimilarity(a, b []float64) float64 {
	if len(a) != len(b) {
		return 0.0
	}

	dotProduct := floats.Dot(a, b)
	normA := floats.Norm(a, 2)
	normB := floats.Norm(b, 2)

	if normA == 0 || normB == 0 {
		return 0.0
	}

	return dotProduct / (normA * normB)
}

func CalculateCosineSimilarityOnMatrix(scores *mat.Dense, gt []float64) []float64 {
	rows, _ := scores.Dims()

	cosineSimilarityArray := make([]float64, rows)

	for rowIdx := range rows {
		rowScores := mat.Row(nil, rowIdx, scores)

		cosineSimilarity := CalculateCosineSimilarity(rowScores, gt)

		if math.IsNaN(cosineSimilarity) {
			cosineSimilarity = 0.0
		}

		cosineSimilarityArray[rowIdx] = cosineSimilarity
	}

	return cosineSimilarityArray
}
