package chainutils

import (
	"fmt"
	"math"
)

const (
	U16MAX = 65535
)

func ConvertWeightsAndUidsForEmit(uids []int64, weights []float64) ([]int, []int, error) {
	if len(uids) != len(weights) {
		return nil, nil, fmt.Errorf("uids and weights must have the same length, got %d and %d", len(uids), len(weights))
	}
	if len(uids) == 0 {
		return []int{}, []int{}, nil
	}

	maxWeight := 0.0
	for i, w := range weights {
		if w < 0 {
			return nil, nil, fmt.Errorf("weights cannot be negative: %v", weights)
		}
		if uids[i] < 0 {
			return nil, nil, fmt.Errorf("uids cannot be negative: %v", uids)
		}
		if w > maxWeight {
			maxWeight = w
		}
	}

	if maxWeight == 0 {
		return []int{}, []int{}, nil
	}

	weightUids := make([]int, 0, len(uids))
	weightVals := make([]int, 0, len(weights))

	for i, w := range weights {
		uint16Val := int(math.Round((w / maxWeight) * float64(U16MAX)))

		if uint16Val > 0 {
			weightUids = append(weightUids, int(uids[i]))
			weightVals = append(weightVals, uint16Val)
		}
	}

	return weightUids, weightVals, nil
}
