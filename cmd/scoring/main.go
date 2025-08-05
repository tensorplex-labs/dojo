package main

import (
	"fmt"
	"math/rand/v2"

	"github.com/rs/zerolog"
	"github.com/tensorplex-labs/dojo/internal/scoring"
	"github.com/tensorplex-labs/dojo/pkg/utils/logger"
	"gonum.org/v1/gonum/mat"
)

func main() {
	logger.Init()
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix

	// Example: 10 miners for better visualization
	numMiners := 10
	numScores := 4
	randomData := make([]float64, numMiners*numScores)
	for i := range randomData {
		randomData[i] = rand.Float64() * 100
	}

	testMatrix := mat.NewDense(numMiners, numScores, randomData)
	gt := scoring.GroundTruthRank([]float64{1, 2, 3, 4})

	pipeline := scoring.CubicScoringPipeline(
		scoring.WithScaling(0.009),
		scoring.WithTranslation(6.0),
		// scoring.WithOffset(3.0),
	)
	processed := pipeline.Process(testMatrix, gt)

	// Plot the cubic reward scores
	logger.Sugar().Infow("Cubic Reward Scores")
	scoring.PlotMinerScoresTerminal(processed.CubicRewardMinerScores, "Cubic Reward Scores")

	logger.Sugar().
		Infow("Raw Scores Stats", "number of miners", numMiners, "number of score responses", numScores)
	fmt.Printf(
		"Raw Scores Matrix:\n  %.2f\n",
		mat.Formatted(testMatrix, mat.Prefix("  "), mat.Squeeze()),
	)

	logger.Sugar().
		Infow("Min-Max Scaled Scores", "number of miners", numMiners, "number of score responses", numScores)
	fmt.Printf(
		"Min-Max Scaled Scores Matrix:\n  %.2f\n",
		mat.Formatted(processed.MinMaxMinerScores, mat.Prefix("  "), mat.Squeeze()),
	)

	logger.Sugar().Infow("Raw Cosine Similarity")
	scoring.PlotMinerScoresTerminal(processed.CosineSimilarityMinerScores, "Raw Cosine Similarity")

	logger.Sugar().Infow("Normalized Cosine Similarity")
	scoring.PlotMinerScoresTerminal(
		processed.NormalisedCosineSimilarityMinerScores,
		"Normalized Cosine Similarity",
	)

	logger.Sugar().Infow("Final Cubic Reward Scores")
	scoring.PlotMinerScoresTerminal(processed.CubicRewardMinerScores, "Final Cubic Reward Scores")
}
