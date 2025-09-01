package scoring

import (
	"gonum.org/v1/gonum/mat"
)

// TODO: remove v1 scoring
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

func CalcPvPScores(discriminators map[string]string, generators map[string]string) (scores map[string]float64) {
	/*
	@param discriminators: map of discriminator addresses to their votes. A 'vote' is represented by the unique ID of selected code output. 
	@param generators: map of generator addresses to their generated output ID.
	@return scores: map of addresses to their scores

	- discriminators receive 1 / totalDiscriminators score irrespective of their vote
	- generators receive num_votes * 1 / totalDiscriminators score
	*/
	scores = make(map[string]float64)

	// 1. tally votes + calculate discriminator scores
	totalDiscriminators := len(discriminators)
	voteCounts := make(map[string]int)
	for addr, vote := range discriminators {
		scores[addr] = 1.0 / float64(totalDiscriminators)
		voteCounts[vote]++
	}

	// 2. calculate generator scores
	for addr, id := range generators {
		scores[addr] = float64(voteCounts[id]) * float64(1.0 / totalDiscriminators)
	}

	return scores
}

func CalcTrapScores(discriminators map[string]string, positiveGenerators map[string]string, negativeGenerators map[string]string) (scores map[string]float64) {
	/*
	@param discriminators: map of discriminator addresses to their votes. A 'vote' is represented by the unique ID of selected code output.
	@param positiveGenerators: map of generator addresses to the superior output ID.
	@param negativeGenerators: map of generator addresses to the inferior output ID.
	@return scores: map of addresses to their scores

	- generators receive no scores
	- discriminators that vote correctly receive no scores
	- discriminators that vote for the 'trap' output receive -1 score
	*/

	scores = make(map[string]float64)

	// tally votes
	voteCounts := make(map[string]int)
	for _, vote := range discriminators {
		voteCounts[vote]++
	}
	// calculate discriminator penalty scores.
	for addr, vote := range discriminators {
		if _, isNegative := negativeGenerators[vote]; isNegative {
			scores[addr] = -1.0
		}
	}

	return scores
}

func CalcPvVScores(discriminators map[string]string, generators map[string]string, validators map[string]string) (scores map[string]float64) {
	/*
	@param discriminators: map of discriminator addresses to their votes. A 'vote' is represented by the unique ID of selected code output.
	@param generators: map of generator addresses to their generated output ID.
	@param validators: map of validator addresses to their generated output ID.
	@return scores: map of addresses to their scores

	- discriminator that voted for validator output gets 1/100 score
	- discriminator that voted for generator output gets nothing
	- generator gains  1 - num_votes * 1/ totalDiscriminators
	*/

	scores = make(map[string]float64)
	// tally votes
	voteCounts := make(map[string]int)
	for _, vote := range discriminators {
		voteCounts[vote]++
	}

	// calculate discriminator scores
	totalDiscriminators := len(discriminators)
	for addr, vote := range discriminators {
		if _, isValidator := validators[vote]; isValidator {
			scores[addr] = 1.0 / float64(totalDiscriminators)
		}
	}

	// calculate generator scores
	for addr, vote := range generators {
		if _, isGenerator := generators[vote]; isGenerator {
			scores[addr] = float64(voteCounts[addr]) * float64(1.0 / totalDiscriminators)
		}
	}

	return scores
}