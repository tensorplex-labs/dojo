package scoring

import (
	"fmt"
	"sort"
	"strings"
)

func PlotMinerScoresTerminal(scores []float64, title string) {
	type MinerScore struct {
		MinerID int
		Score   float64
	}

	minerScoresStruct := make([]MinerScore, len(scores))
	for i := range scores {
		minerScoresStruct[i] = MinerScore{
			MinerID: i,
			Score:   scores[i],
		}
	}

	// Sort by score in ascending order
	sort.Slice(minerScoresStruct, func(i, j int) bool {
		return minerScoresStruct[i].Score < minerScoresStruct[j].Score
	})

	// Find min and max for scaling
	minScore := minerScoresStruct[0].Score
	maxScore := minerScoresStruct[len(minerScoresStruct)-1].Score

	fmt.Printf("\n%s (Terminal Plot - Ascending Order):\n", title)
	fmt.Println("Miner ID | Score    | Bar Chart")
	fmt.Println("---------|----------|" + strings.Repeat("-", 50))

	// Plot each score as a horizontal bar
	maxBarWidth := 50
	for _, ms := range minerScoresStruct {
		// Normalize score to bar width
		var barWidth int
		if maxScore != minScore {
			barWidth = int((ms.Score - minScore) / (maxScore - minScore) * float64(maxBarWidth))
		} else {
			barWidth = maxBarWidth / 2
		}

		// Create bar
		bar := strings.Repeat("█", barWidth)
		if barWidth == 0 {
			bar = "▏"
		}

		fmt.Printf("%8d | %.6f | %s (%.4f)\n", ms.MinerID, ms.Score, bar, ms.Score)
	}

	fmt.Printf("\nScale: Min=%.6f, Max=%.6f\n", minScore, maxScore)
	fmt.Printf("Bar width represents relative score (0 to %d chars)\n", maxBarWidth)
}
