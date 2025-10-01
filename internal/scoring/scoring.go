// Package scoring contains logic to execute and calculate scoring
package scoring

import (
	"github.com/rs/zerolog/log"
)

const trapPenalty = -0.5

func CalcPvPScores(discriminators, generators map[string]string) (scores map[string]float64) {
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

	generatorTaskIDToAddrs := make(map[string]string, len(generators))
	for addr, outputID := range generators {
		generatorTaskIDToAddrs[outputID] = addr
	}

	for addr, vote := range discriminators {
		scores[addr] = 1.0 / float64(totalDiscriminators)
		voteCounts[vote]++
		log.Debug().Msgf("Discriminator (%s) voted for Generator (%s) and scores: %f", addr, generatorTaskIDToAddrs[vote], scores[addr])
	}

	// 2. calculate generator scores
	for addr, id := range generators {
		scores[addr] = float64(voteCounts[id]) * (1.0 / float64(totalDiscriminators))
		log.Debug().Msgf("Generator (%s) received %d votes and scores: %f", addr, voteCounts[id], scores[addr])
	}
	log.Debug().Msgf("Final Scores: %+v", scores)
	return scores
}

func CalcTrapScores(discriminators, positiveGenerators, negativeGenerators map[string]string) (scores map[string]float64) {
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

	negativeGeneratorTaskIDToAddrs := make(map[string]string, len(negativeGenerators))
	for addr, outputID := range negativeGenerators {
		negativeGeneratorTaskIDToAddrs[outputID] = addr
	}

	negativeOutputs := make(map[string]bool)
	for _, outputID := range negativeGenerators {
		negativeOutputs[outputID] = true
	}

	for addr, vote := range discriminators {
		if negativeOutputs[vote] {
			scores[addr] = trapPenalty
			log.Debug().Msgf("Discriminator (%s) voted for Trap Generator (%s) and scores: %f", addr, negativeGeneratorTaskIDToAddrs[vote], scores[addr])
		} else {
			scores[addr] = 0.0
			log.Debug().Msgf("Discriminator (%s) did not vote for Trap Generator (%s) and scores: %f", addr, negativeGeneratorTaskIDToAddrs[vote], scores[addr])
		}
	}

	log.Debug().Msgf("Final Scores: %+v", scores)

	return scores
}

func CalcPvVScores(discriminators, generators, validators map[string]string) (scores map[string]float64) {
	/*
		@param discriminators: map of discriminator addresses to their votes. A 'vote' is represented by the unique ID of selected code output.
		@param generators: map of generator addresses to their generated output ID.
		@param validators: map of validator addresses to their generated output ID.
		@return scores: map of addresses to their scores

		- discriminator that voted for validator output gets 1/ totalDiscriminators score
		- discriminator that voted for generator output gets nothing
		- generator gains  1 - num_votes * 1/ totalDiscriminators
	*/

	scores = make(map[string]float64)

	generatorTaskIDToAddrs := make(map[string]string, len(generators))
	for addr, outputID := range generators {
		generatorTaskIDToAddrs[outputID] = addr
	}

	validatorOutputs := make(map[string]bool)
	for _, outputID := range validators {
		validatorOutputs[outputID] = true
	}

	// tally votes
	voteCounts := make(map[string]int)
	for _, vote := range discriminators {
		voteCounts[vote]++
	}

	// calculate discriminator scores
	totalDiscriminators := len(discriminators)
	for addr, vote := range discriminators {
		if validatorOutputs[vote] {
			scores[addr] = 1.0 / float64(totalDiscriminators)
			log.Debug().Msgf("Discriminator (%s) voted for Validator and scores: %f", addr, scores[addr])
		} else {
			scores[addr] = 0.0
			log.Debug().Msgf("Discriminator (%s) voted for Generator (%s) and scores: %f", addr, generatorTaskIDToAddrs[vote], scores[addr])
		}
	}

	// calculate generator scores
	for addr, outputID := range generators {
		scores[addr] = float64(voteCounts[outputID]) * (1.0 / float64(totalDiscriminators))
		log.Debug().Msgf("Generator (%s) received %d votes and scores: %f", addr, voteCounts[outputID], scores[addr])
	}

	log.Debug().Msgf("Final Scores: %+v", scores)
	return scores
}
