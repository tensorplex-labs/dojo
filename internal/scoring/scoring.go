// Package scoring contains logic to execute and calculate scoring
package scoring

import (
	"slices"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/samber/lo"

	"github.com/tensorplex-labs/dojo/internal/taskapi"
)

const (
	TrapPenalty                       = -0.5
	TrapPenaltyTransferFactor         = 0.5
	TrapPositiveGeneratorRewardFactor = 0.003
	NoVotePenaltyTotalDistribution    = -4.0
)

type TaskScoringInput struct {
	TaskID                     string                   // taskID to score
	Completions                []taskapi.VoteCompletion // completions of the tasks to score
	Votes                      []taskapi.VoteData       // votes of the tasks to score
	IsTrap                     bool                     // whether the task is a trap
	NegativeGeneratorHotkey    string                   // hotkey of the negative generator if it is a trap
	ValidatorHotkey            string
	Voters                     []string // voters assigned to this task
	CurrentActiveMinersHotkeys []string // active miners hotkeys
}

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

		- discriminators that vote correctly for positiveGenerators receive no scores
		- discriminators that vote for the 'negativeGenerators receive a penalty score of TrapPenalty
		- the penalty score is transferred to the negativeGenerators in proportion to their weight
		- the positiveGenerators receive a reward score of TrapPositiveGeneratorRewardFactor * votes for the positiveGenerators
	*/

	negOutputToAddr := lo.Invert(negativeGenerators)
	posOutputToAddr := lo.Invert(positiveGenerators)

	scores = make(map[string]float64, len(discriminators)+len(negativeGenerators)+len(positiveGenerators))
	negVotes := make(map[string]int, len(negativeGenerators))
	posVotes := make(map[string]int, len(positiveGenerators))

	lo.ForEach(lo.Entries(discriminators), func(e lo.Entry[string, string], _ int) {
		addr, vote := e.Key, e.Value

		if genAddr, ok := negOutputToAddr[vote]; ok {
			scores[addr] = TrapPenalty
			negVotes[genAddr]++
		} else if genAddr, ok := posOutputToAddr[vote]; ok {
			scores[addr] = 0.0
			posVotes[genAddr]++
		} else {
			scores[addr] = 0.0
		}
	})

	lo.ForEach(lo.Keys(negativeGenerators), func(addr string, _ int) {
		scores[addr] = -TrapPenalty * TrapPenaltyTransferFactor * float64(negVotes[addr])
	})

	lo.ForEach(lo.Keys(positiveGenerators), func(addr string, _ int) {
		scores[addr] = TrapPositiveGeneratorRewardFactor * float64(posVotes[addr])
	})

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

func CalculateTaskScores(taskScoringInput *TaskScoringInput) (scores map[string]float64) {
	startTime := time.Now()
	completionMaps := CategorizeCompletions(taskScoringInput.Completions, taskScoringInput.IsTrap, taskScoringInput.NegativeGeneratorHotkey, taskScoringInput.ValidatorHotkey)
	discriminators := BuildDiscriminatorsMap(taskScoringInput.Votes)

	if len(discriminators) == 0 {
		return make(map[string]float64)
	}

	taskType := DetermineTaskType(completionMaps, taskScoringInput.IsTrap)

	switch taskType {
	case "Trap":
		log.Debug().Msgf("Calculating trap score for task %s", taskScoringInput.TaskID)
		scores = CalcTrapScores(discriminators, completionMaps.PositiveGenerators, completionMaps.NegativeGenerators)
	case "PvP":
		log.Debug().Msgf("Calculating PvP score for task %s", taskScoringInput.TaskID)
		scores = CalcPvPScores(discriminators, completionMaps.Generators)
	case "PvV":
		log.Debug().Msgf("Calculating PvV score for task %s", taskScoringInput.TaskID)
		scores = CalcPvVScores(discriminators, completionMaps.Generators, completionMaps.Validator)
	}

	nonVoterAddresses := FindNonVoters(scores, taskScoringInput.CurrentActiveMinersHotkeys, taskScoringInput.Voters)

	noVotePenalty := CalculateNoVotePenalty(nonVoterAddresses)
	log.Debug().Msgf("There are %d non-voters for the task %s, so the no vote penalty for each non-voter is %f", len(nonVoterAddresses), taskScoringInput.TaskID, noVotePenalty)
	for _, nonVoter := range nonVoterAddresses {
		scores[nonVoter] = noVotePenalty
		log.Debug().Msgf("hotkey %s did not vote for task %s, adding no vote penalty of %f", nonVoter, taskScoringInput.TaskID, noVotePenalty)
	}

	if len(scores) == 0 {
		scores = make(map[string]float64)
	}

	log.Debug().Msgf("Calculated task scores successfully for task %s in %v", taskScoringInput.TaskID, time.Since(startTime))
	return scores
}

type CompletionMaps struct {
	Validator          map[string]string
	Generators         map[string]string
	PositiveGenerators map[string]string
	NegativeGenerators map[string]string
}

func CategorizeCompletions(
	completions []taskapi.VoteCompletion,
	isTrap bool,
	negativeGeneratorHotkey,
	validatorHotkey string,
) CompletionMaps {
	completionMaps := CompletionMaps{
		Validator:          make(map[string]string),
		Generators:         make(map[string]string),
		PositiveGenerators: make(map[string]string),
		NegativeGenerators: make(map[string]string),
	}

	for _, completion := range completions {
		if isTrap {
			if completion.ParticipantHotkey == negativeGeneratorHotkey {
				completionMaps.NegativeGenerators[completion.ParticipantHotkey] = completion.ID
			} else {
				completionMaps.PositiveGenerators[completion.ParticipantHotkey] = completion.ID
			}
		} else {
			if completion.ParticipantHotkey == validatorHotkey {
				completionMaps.Validator[completion.ParticipantHotkey] = completion.ID
			} else {
				completionMaps.Generators[completion.ParticipantHotkey] = completion.ID
			}
		}
	}

	return completionMaps
}

func BuildDiscriminatorsMap(votes []taskapi.VoteData) map[string]string {
	discriminators := make(map[string]string)

	for _, vote := range votes {
		discriminators[vote.VoterHotkey] = vote.ChosenCompletionID
	}

	return discriminators
}

func DetermineTaskType(completionMaps CompletionMaps, isTrap bool) string {
	if isTrap {
		return "Trap"
	} else if len(completionMaps.Validator) == 0 {
		return "PvP"
	} else {
		return "PvV"
	}
}

func FindNonVoters(scores map[string]float64, currentActiveMinersHotkeys, voters []string) (nonVoterAddresses []string) {
	for _, hotkey := range currentActiveMinersHotkeys {
		if _, exists := scores[hotkey]; !exists && slices.Contains(voters, hotkey) {
			nonVoterAddresses = append(nonVoterAddresses, hotkey)
		}
	}

	return nonVoterAddresses
}

func CalculateNoVotePenalty(nonVoterAddresses []string) float64 {
	if len(nonVoterAddresses) == 0 {
		log.Info().Msgf("No non-voters")
		return 0.0
	}
	return NoVotePenaltyTotalDistribution / float64(len(nonVoterAddresses))
}

func AggregateTaskScoresByUID(
	allTaskScores map[string]map[string]float64,
	hotkeys []string,
) []float64 {
	hotkeyToUID := make(map[string]int)
	for uid, hotkey := range hotkeys {
		hotkeyToUID[hotkey] = uid
	}
	scores := make([]float64, len(hotkeys))

	for taskID, taskScores := range allTaskScores {
		for hotkey, score := range taskScores {
			if uid, exists := hotkeyToUID[hotkey]; exists {
				scores[uid] += score
				log.Debug().Str("hotkey", hotkey).Str("taskID", taskID).Float64("score", score).
					Msgf("hotkey %s scored %f for task %s", hotkey, score, taskID)
			} else {
				log.Debug().Str("hotkey", hotkey).Str("taskID", taskID).
					Msg("hotkey not found in metagraph")
			}
		}
	}

	return scores
}
