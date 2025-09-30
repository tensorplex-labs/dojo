package main

import (
	"fmt"
	"os"

	"github.com/bytedance/sonic"
	tea "github.com/charmbracelet/bubbletea"

	"github.com/tensorplex-labs/dojo/internal/config"
	"github.com/tensorplex-labs/dojo/internal/kami"
	chainutils "github.com/tensorplex-labs/dojo/internal/utils/chain_utils"
)

type ScoreConfig struct {
	Scores  []float64 `json:"scores"`
	Step    int       `json:"step"`
	Hotkeys []string  `json:"hotkeys"`
}

type model struct {
	choices       []string
	ids           []int64
	cursor        int
	selectedIndex int // single selection index; -1 until chosen
	kamiClient    *kami.Kami
	chainConfig   *config.ChainEnvConfig
}

func initialModel() *model {
	cfg, err := config.LoadConfig()
	if err != nil {
		fmt.Printf("Error loading config: %v\n", err)
		os.Exit(1)
	}

	k, err := kami.NewKami(&cfg.KamiEnvConfig)
	if err != nil {
		fmt.Printf("Error initializing Kami: %v\n", err)
		os.Exit(1)
	}

	return &model{
		choices:       []string{"Set 100% burn weight", "Set scores weight"},
		ids:           []int64{0, 1},
		cursor:        0,
		selectedIndex: -1,
		chainConfig:   &cfg.ChainEnvConfig,
		kamiClient:    k,
	}
}

func (m *model) Update(msg tea.Msg) (tea.Model, tea.Cmd) { //nolint
	switch msg := msg.(type) { //nolint
	case tea.KeyMsg:
		switch msg.String() {
		// These keys should exit the program.
		case "ctrl+c", "q":
			return m, tea.Quit

		// The "up" and "k" keys move the cursor up
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}

		// The "down" and "j" keys move the cursor down
		case "down", "j":
			if m.cursor < len(m.choices)-1 {
				m.cursor++
			}

		// The "enter" key confirms the current cursor selection.
		case "enter":
			m.selectedIndex = m.cursor
			switch m.selectedIndex {
			case 0:
				fmt.Println("Setting 100% burn weight to uid 158")
				uids := []int{158}
				weights := []int{65536}

				payload := kami.SetWeightsParams{
					Netuid:     m.chainConfig.Netuid,
					Dests:      uids,
					Weights:    weights,
					VersionKey: 1,
				}

				res, err := m.kamiClient.SetWeights(payload)
				if err != nil {
					fmt.Printf("Error setting weights: %v\n", err)
					return m, tea.Quit
				}

				fmt.Printf("Successfully set weights with hash: %s\n", res.Data)

				fmt.Println("Successfully set burn weights!")
			case 1:
				fmt.Println("Setting scores weight")
				latestScoresData, err := os.ReadFile("scores.json")
				if err != nil {
					fmt.Printf("failed to read scores file: %v\n", err)
					return m, tea.Quit
				}

				var scores ScoreConfig
				if err = sonic.Unmarshal(latestScoresData, &scores); err != nil {
					fmt.Printf("failed to unmarshal scores file data: %v\n", err)
					return m, tea.Quit
				}

				uids := make([]int64, len(scores.Scores))
				for i := range uids {
					uids[i] = int64(i)
				}

				weights := chainutils.ClampNegativeWeights(scores.Scores)

				convertedUids, convertedWeights, err := chainutils.ConvertWeightsAndUidsForEmit(uids, weights)
				if err != nil {
					fmt.Printf("Error converting weights and uids: %v\n", err)
					return m, tea.Quit
				}

				payload := kami.SetWeightsParams{
					Netuid:     m.chainConfig.Netuid,
					Dests:      convertedUids,
					Weights:    convertedWeights,
					VersionKey: 1,
				}

				res, err := m.kamiClient.SetWeights(payload)
				if err != nil {
					fmt.Printf("Error setting weights: %v\n", err)
					return m, tea.Quit
				}

				fmt.Printf("Successfully set weights with hash: %s", res.Data)

			default:
				fmt.Println("Unknown selection")
			}

			return m, tea.Quit
		}
	}

	// Return the updated model to the Bubble Tea runtime for processing.
	// Note that we're not returning a command.
	return m, nil
}

func (m *model) View() string {
	// The header
	s := "Select an option:\n\n"

	// Iterate over our choices
	for i, choice := range m.choices {
		// Is the cursor pointing at this choice?
		cursor := " " // no cursor
		if m.cursor == i {
			cursor = ">" // cursor!
		}

		// Render the row
		s += fmt.Sprintf("%s %s\n", cursor, choice)
	}

	// The footer
	s += "\nPress q to quit.\n"

	// Send the UI for rendering
	return s
}

func (m *model) Init() tea.Cmd {
	// Just return `nil`, which means "no I/O right now, please."
	return nil
}

func main() {
	p := tea.NewProgram(initialModel())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Alas, there's been an error: %v", err)
		os.Exit(1)
	}
}
