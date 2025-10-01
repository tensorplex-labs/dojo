package chainutils

import (
	"fmt"
	"math"

	"github.com/rs/zerolog/log"
)

const (
	U16MAX     = 65535
	BurnUID    = 158
	BurnWeight = 80
)

func ClampNegativeWeights(weights []float64) []float64 {
	clamped := make([]float64, len(weights))
	for i, w := range weights {
		if w < 0 {
			clamped[i] = 0
		} else {
			clamped[i] = w
		}
	}
	return clamped
}

func ConvertWeightsAndUidsForEmit(uids []int64, weights []float64) (finalisedUids, convertedWeights []int, err error) {
	if len(uids) != len(weights) {
		return nil, nil, fmt.Errorf("uids and weights must have the same length, got %d and %d", len(uids), len(weights))
	}
	if len(uids) == 0 || len(weights) == 0 {
		return []int{}, []int{}, fmt.Errorf("uids or weights cannot be empty")
	}

	maxWeightForNormalization := 0.0
	totalWeightForNormalization := 0.0

	for i, w := range weights {
		if w < 0 {
			return nil, nil, fmt.Errorf("weights cannot be negative: %v", weights)
		}
		if uids[i] < 0 {
			return nil, nil, fmt.Errorf("uids cannot be negative: %v", uids)
		}

		if uids[i] != BurnUID {
			if w > maxWeightForNormalization {
				maxWeightForNormalization = w
			}
			totalWeightForNormalization += w
		}
	}

	if totalWeightForNormalization == 0 {
		if BurnWeight > 0 {
			return []int{BurnUID}, []int{int(math.Round(0.01 * BurnWeight * U16MAX))}, nil
		}
		return []int{}, []int{}, fmt.Errorf("no weights to set")
	}

	weightUids := make([]int, 0, len(uids))
	weightVals := make([]int, 0, len(weights))

	preBurnUids := make([]int, 0, len(uids))
	preBurnVals := make([]int, 0, len(weights))

	for i, uid := range uids {
		var finalWeight, preBurnWeight float64

		if uid == BurnUID {
			finalWeight = BurnWeight / 100.0
			preBurnWeight = 0.0
		} else {
			normalizedWeight := weights[i] / maxWeightForNormalization
			proportionalShare := normalizedWeight / (totalWeightForNormalization / maxWeightForNormalization)
			finalWeight = proportionalShare * (1 - BurnWeight/100.0)
			preBurnWeight = proportionalShare
		}

		uint16Val := int(math.Round(finalWeight * float64(U16MAX)))
		if uint16Val > 0 {
			weightUids = append(weightUids, int(uid))
			weightVals = append(weightVals, uint16Val)
		}

		preBurnUInt16Val := int(math.Round(preBurnWeight * float64(U16MAX)))
		if preBurnUInt16Val > 0 {
			preBurnUids = append(preBurnUids, int(uid))
			preBurnVals = append(preBurnVals, preBurnUInt16Val)
		}
	}

	log.Info().Msgf("Pre burn weights: uids: %v, weights: %v", preBurnUids, preBurnVals)

	return weightUids, weightVals, nil
}
