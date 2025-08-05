package scoring

import (
	"fmt"
	"math/rand/v2"
	"testing"

	"gonum.org/v1/gonum/mat"
)

// Benchmark the MinMaxsScale function
func BenchmarkMinMaxsScale(b *testing.B) {
	// Setup test data
	numMiners := 250
	numScores := 4
	randomData := make([]float64, numMiners*numScores)
	for i := range randomData {
		randomData[i] = rand.Float64() * 100
	}

	testMatrix := mat.NewDense(numMiners, numScores, randomData)
	gt := GroundTruthRank([]float64{1, 2, 3, 4})

	b.ResetTimer() // Reset timer after setup

	for b.Loop() {
		_ = ProcessMinerRawScoresWithGroundTruth(testMatrix, gt, DefaultCubicParams())
	}
}

// Benchmark with different matrix sizes
func BenchmarkCalculateMinerRawScores(b *testing.B) {
	sizes := []struct {
		miners int
		scores int
	}{
		{250, 4},
		{250, 5},
		{250, 10},
	}

	for _, size := range sizes {
		b.Run(fmt.Sprintf("Miners%d_Scores%d", size.miners, size.scores), func(b *testing.B) {
			randomData := make([]float64, size.miners*size.scores)
			for i := range randomData {
				randomData[i] = rand.Float64() * 100
			}

			testMatrix := mat.NewDense(size.miners, size.scores, randomData)
			gt := GroundTruthRank(make([]float64, size.scores))

			b.ResetTimer()
			for b.Loop() {
				_ = ProcessMinerRawScoresWithGroundTruth(testMatrix, gt, DefaultCubicParams())
			}
		})
	}
}
