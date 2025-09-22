package chainutils

import (
	"fmt"
	"math"
)

const (
	U16MAX     = 65535
	BurnUID    = 158
	BurnWeight = 95
)

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
		return []int{}, []int{}, fmt.Errorf("no weights to set")
	}

	weightUids := make([]int, 0, len(uids))
	weightVals := make([]int, 0, len(weights))

	for i, uid := range uids {
		var finalWeight float64

		if uid == BurnUID {
			finalWeight = BurnWeight / 100.0
		} else {
			normalizedWeight := weights[i] / maxWeightForNormalization
			proportionalShare := normalizedWeight / (totalWeightForNormalization / maxWeightForNormalization)
			finalWeight = proportionalShare * (1 - BurnWeight/100.0)
		}

		uint16Val := int(math.Round(finalWeight * float64(U16MAX)))
		if uint16Val > 0 {
			weightUids = append(weightUids, int(uid))
			weightVals = append(weightVals, uint16Val)
		}
	}

	return weightUids, weightVals, nil
}
