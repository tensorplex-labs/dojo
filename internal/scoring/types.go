package scoring

import "gonum.org/v1/gonum/mat"

type GroundTruthRank []float64 // 1D: ground truth rank

type ProcessedMinerScoreMatrix struct {
	MinMaxMinerScores                     *mat.Dense // 2D: min-max scaled scores per miner
	CosineSimilarityMinerScores           []float64  // 1D: cosine similarity with ground truth
	NormalisedCosineSimilarityMinerScores []float64  // 1D: normalized cosine similarities
	CubicRewardMinerScores                []float64  // 1D: final cubic reward scores
}
