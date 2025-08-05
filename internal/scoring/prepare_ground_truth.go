package scoring

import "sort"

func PrepareGroundTruth(gt GroundTruthRank) []float64 {

	sorted_gt := make([]float64, len(gt))
	copy(sorted_gt, gt)
	sort.Slice(sorted_gt, func(i, j int) bool {
		return sorted_gt[i] > sorted_gt[j]
	})

	return sorted_gt
}
