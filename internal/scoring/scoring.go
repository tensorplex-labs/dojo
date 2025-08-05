package scoring

import (
	"gonum.org/v1/gonum/mat"
)

// Process all scoring stages
func ProcessMinerRawScoresWithGroundTruth(minerRawScores *mat.Dense, gt GroundTruthRank, cubicParams CubicParams) ProcessedMinerScoreMatrix {
	// Stage 0: Sort and Min-Max GroundTruth
	sorted_gt := PrepareGroundTruth(gt)
	minMaxScaledGroundTruth := MinMaxScale(sorted_gt)

	// Stage 1: Min-Max scaling
	minMaxScores := MinMaxScaleOnMatrix(minerRawScores)

	// Stage 2: Cosine similarity with ground truth (range [-1, 1])
	cosineSimilarity := CalculateCosineSimilarityOnMatrix(minMaxScores, minMaxScaledGroundTruth)

	// Stage 3: Transform cosine similarity to range [0, 1]
	transformedCosineSimilarity := TransformToRange01(cosineSimilarity)

	// Stage 4: L1 normalization to sum=1
	normalizedCosineSimilarity := L1Normalize(transformedCosineSimilarity)

	// Stage 5: Apply cubic reward transformation
	cubicTransformedRewards := ApplyCubicTransformation(normalizedCosineSimilarity, cubicParams.Scaling, cubicParams.Translation, cubicParams.Offset)

	// Stage 6: Min-Max scaling
	minMaxScaledCubicTransformedRewards := MinMaxScale(cubicTransformedRewards)

	// Stage 7: L1 normalization to sum=1
	normalizedMinMaxScaledCubicTransformedRewards := L1Normalize(minMaxScaledCubicTransformedRewards)

	return ProcessedMinerScoreMatrix{
		MinMaxMinerScores:                     minMaxScores,
		CosineSimilarityMinerScores:           cosineSimilarity,
		NormalisedCosineSimilarityMinerScores: normalizedCosineSimilarity,
		CubicRewardMinerScores:                normalizedMinMaxScaledCubicTransformedRewards,
	}
}
