package kami

import (
	"encoding/json"
	"fmt"
	"math/big"
	"strconv"
	"strings"
)

// HexOrInt handles fields that can be either a number or a hex string
// It uses big.Int internally to handle arbitrarily large values without overflow
type HexOrInt struct {
	Value *big.Int
}

// UnmarshalJSON accepts numbers (e.g. 12345) or strings ("0xabc" or "12345")
func (h *HexOrInt) UnmarshalJSON(b []byte) error {
	if len(b) == 0 || string(b) == "null" {
		h.Value = big.NewInt(0)
		return nil
	}

	var s string
	if b[0] == '"' {
		if err := json.Unmarshal(b, &s); err != nil {
			return err
		}
	} else {
		s = string(b)
	}

	s = strings.TrimSpace(s)
	if s == "" {
		h.Value = big.NewInt(0)
		return nil
	}

	v := new(big.Int)
	if strings.HasPrefix(s, "0x") || strings.HasPrefix(s, "0X") {
		if _, ok := v.SetString(s[2:], 16); !ok {
			return fmt.Errorf("invalid hex integer: %s", s)
		}
	} else {
		if _, ok := v.SetString(s, 10); !ok {
			return fmt.Errorf("invalid decimal integer: %s", s)
		}
	}
	h.Value = v
	return nil
}

type KamiResponse[T any] struct {
	StatusCode int            `json:"statusCode"`
	Success    bool           `json:"success"`
	Data       T              `json:"data"`
	Error      map[string]any `json:"error"`
}

type (
	SubnetMetagraphResponse   = KamiResponse[SubnetMetagraph]
	LatestBlockResponse       = KamiResponse[LatestBlock]
	KeyringPairInfoResponse   = KamiResponse[KeyringPairInfo]
	SubnetHyperparamsResponse = KamiResponse[SubnetHyperparams]
	CheckHotkeyResponse       = KamiResponse[CheckHotkey]
	AccountNonceResponse      = KamiResponse[AccountNonce]
	SignMessageResponse       = KamiResponse[SignMessage]
	VerifyMessageResponse     = KamiResponse[VerifyMessage]
	ExtrinsicHashResponse     = KamiResponse[string]
)

type MovingPrice struct {
	Bits int `json:"bits"`
}

type DividendEntry struct {
	Hotkey string
	Amount float64
}

func (d *DividendEntry) UnmarshalJSON(b []byte) error {
	// try object form first
	type obj DividendEntry
	var o obj
	if err := json.Unmarshal(b, &o); err == nil {
		*d = DividendEntry(o)
		return nil
	}

	// try array form: [hotkey, amount]
	var arr []any
	if err := json.Unmarshal(b, &arr); err != nil {
		return fmt.Errorf("invalid dividend entry: %w", err)
	}
	if len(arr) < 2 {
		return fmt.Errorf("dividend array must have at least 2 elements")
	}

	hot, ok := arr[0].(string)
	if !ok {
		return fmt.Errorf("expected hotkey string, got %T", arr[0])
	}

	var amt float64
	switch v := arr[1].(type) {
	case nil:
		amt = 0
	case float64:
		amt = v
	case string:
		if v == "" {
			amt = 0
		} else {
			f, err := strconv.ParseFloat(v, 64)
			if err != nil {
				return fmt.Errorf("parse amount string: %w", err)
			}
			amt = f
		}
	default:
		// fallback: stringify then parse
		s := fmt.Sprintf("%v", v)
		f, err := strconv.ParseFloat(s, 64)
		if err != nil {
			return fmt.Errorf("unsupported amount type %T", arr[1])
		}
		amt = f
	}

	d.Hotkey = hot
	d.Amount = amt
	return nil
}

// SubnetMetagraph represents the main subnet metagraph structure
type SubnetMetagraph struct {
	Netuid                     int              `json:"netuid"`
	Name                       string           `json:"name"`
	Symbol                     string           `json:"symbol"`
	Identity                   SubnetIdentity   `json:"identity"`
	NetworkRegisteredAt        int              `json:"networkRegisteredAt"`
	OwnerHotkey                string           `json:"ownerHotkey"`
	OwnerColdkey               string           `json:"ownerColdkey"`
	Block                      int              `json:"block"`
	Tempo                      int              `json:"tempo"`
	LastStep                   int              `json:"lastStep"`
	BlocksSinceLastStep        int              `json:"blocksSinceLastStep"`
	SubnetEmission             float64          `json:"subnetEmission"`
	AlphaIn                    float64          `json:"alphaIn"`
	AlphaOut                   float64          `json:"alphaOut"`
	TaoIn                      float64          `json:"taoIn"`
	AlphaOutEmission           float64          `json:"alphaOutEmission"`
	AlphaInEmission            float64          `json:"alphaInEmission"`
	TaoInEmission              float64          `json:"taoInEmission"`
	PendingAlphaEmission       float64          `json:"pendingAlphaEmission"`
	PendingRootEmission        float64          `json:"pendingRootEmission"`
	SubnetVolume               float64          `json:"subnetVolume"`
	MovingPrice                MovingPrice      `json:"movingPrice"`
	Rho                        float64          `json:"rho"`
	Kappa                      float64          `json:"kappa"`
	MinAllowedWeights          int              `json:"minAllowedWeights"`
	MaxAllowedWeights          int              `json:"maxAllowedWeights"`
	WeightsVersion             int              `json:"weightsVersion"`
	WeightsRateLimit           int              `json:"weightsRateLimit"`
	ActivityCutoff             int              `json:"activityCutoff"`
	MaxValidators              int              `json:"maxValidators"`
	NumUids                    int              `json:"numUids"`
	MaxUids                    int              `json:"maxUids"`
	Burn                       float64          `json:"burn"`
	Difficulty                 HexOrInt         `json:"difficulty"`
	RegistrationAllowed        bool             `json:"registrationAllowed"`
	PowRegistrationAllowed     bool             `json:"powRegistrationAllowed"`
	ImmunityPeriod             int              `json:"immunityPeriod"`
	MinDifficulty              HexOrInt         `json:"minDifficulty"`
	MaxDifficulty              HexOrInt         `json:"maxDifficulty"`
	MinBurn                    float64          `json:"minBurn"`
	MaxBurn                    float64          `json:"maxBurn"`
	AdjustmentAlpha            HexOrInt         `json:"adjustmentAlpha"`
	AdjustmentInterval         int              `json:"adjustmentInterval"`
	TargetRegsPerInterval      int              `json:"targetRegsPerInterval"`
	MaxRegsPerBlock            int              `json:"maxRegsPerBlock"`
	ServingRateLimit           int              `json:"servingRateLimit"`
	CommitRevealWeightsEnabled bool             `json:"commitRevealWeightsEnabled"`
	CommitRevealPeriod         int              `json:"commitRevealPeriod"`
	LiquidAlphaEnabled         bool             `json:"liquidAlphaEnabled"`
	AlphaHigh                  float64          `json:"alphaHigh"`
	AlphaLow                   float64          `json:"alphaLow"`
	BondsMovingAvg             float64          `json:"bondsMovingAvg"`
	Hotkeys                    []string         `json:"hotkeys"`
	Coldkeys                   []string         `json:"coldkeys"`
	Identities                 []IdentitiesInfo `json:"identities"`
	Axons                      []AxonInfo       `json:"axons"`
	Active                     []bool           `json:"active"`
	ValidatorPermit            []bool           `json:"validatorPermit"`
	PruningScore               []float64        `json:"pruningScore"`
	LastUpdate                 []int            `json:"lastUpdate"`
	Emission                   []float64        `json:"emission"`
	Dividends                  []float64        `json:"dividends"`
	Incentives                 []float64        `json:"incentives"`
	Consensus                  []float64        `json:"consensus"`
	Trust                      []float64        `json:"trust"`
	Rank                       []float64        `json:"rank"`
	BlockAtRegistration        []int            `json:"blockAtRegistration"`
	AlphaStake                 []float64        `json:"alphaStake"`
	TaoStake                   []float64        `json:"taoStake"`
	TotalStake                 []float64        `json:"totalStake"`
	TaoDividendsPerHotkey      []DividendEntry  `json:"taoDividendsPerHotkey"`
	AlphaDividendsPerHotkey    []DividendEntry  `json:"alphaDividendsPerHotkey"`
}

type SubnetIdentity struct {
	SubnetName    string `json:"subnetName"`
	GithubRepo    string `json:"githubRepo"`
	SubnetContact string `json:"subnetContact"`
	SubnetURL     string `json:"subnetUrl"`
	Discord       string `json:"discord"`
	Description   string `json:"description"`
	Additional    string `json:"additional"`
}

type IdentitiesInfo struct {
	Name        string `json:"name"`
	URL         string `json:"url"`
	GithubRepo  string `json:"githubRepo"`
	Image       string `json:"image"`
	Discord     string `json:"discord"`
	Description string `json:"description"`
	Additional  string `json:"additional"`
}

type AxonInfo struct {
	Block        int    `json:"block"`
	Version      int    `json:"version"`
	IP           string `json:"ip"`
	Port         int    `json:"port"`
	IPType       int    `json:"ipType"`
	Protocol     int    `json:"protocol"`
	Placeholder1 int    `json:"placeholder1"`
	Placeholder2 int    `json:"placeholder2"`
}

type LatestBlock struct {
	ParentHash     string `json:"parentHash"`
	BlockNumber    int    `json:"blockNumber"`
	StateRoot      string `json:"stateRoot"`
	ExtrinsicsRoot string `json:"extrinsicsRoot"`
}

type KeyringPair struct {
	Address    string                 `json:"address"`
	AddressRaw map[string]interface{} `json:"addressRaw"`
	IsLocked   bool                   `json:"isLocked"`
	Meta       map[string]interface{} `json:"meta"`
	PublicKey  map[string]interface{} `json:"publicKey"`
	Type       string                 `json:"type"`
}

type KeyringPairInfo struct {
	KeyringPair   KeyringPair `json:"keyringPair"`
	WalletColdkey string      `json:"walletColdkey"`
}

type SubnetHyperparams struct {
	Rho                        float64 `json:"rho"`
	Kappa                      float64 `json:"kappa"`
	ImmunityPeriod             int     `json:"immunityPeriod"`
	MinAllowedWeights          int     `json:"minAllowedWeights"`
	MaxWeightsLimit            int     `json:"maxWeightsLimit"`
	Tempo                      int     `json:"tempo"`
	MinDifficulty              int64   `json:"minDifficulty"`
	MaxDifficulty              int64   `json:"maxDifficulty"`
	WeightsVersion             int     `json:"weightsVersion"`
	WeightsRateLimit           int     `json:"weightsRateLimit"`
	AdjustmentInterval         int     `json:"adjustmentInterval"`
	ActivityCutoff             int     `json:"activityCutoff"`
	RegistrationAllowed        bool    `json:"registrationAllowed"`
	TargetRegsPerInterval      int     `json:"targetRegsPerInterval"`
	MinBurn                    int64   `json:"minBurn"`
	MaxBurn                    int64   `json:"maxBurn"`
	BondsMovingAvg             int64   `json:"bondsMovingAvg"`
	MaxRegsPerBlock            int     `json:"maxRegsPerBlock"`
	ServingRateLimit           int     `json:"servingRateLimit"`
	MaxValidators              int     `json:"maxValidators"`
	AdjustmentAlpha            string  `json:"adjustmentAlpha"`
	Difficulty                 int64   `json:"difficulty"`
	CommitRevealPeriod         int     `json:"commitRevealPeriod"`
	CommitRevealWeightsEnabled bool    `json:"commitRevealWeightsEnabled"`
	AlphaHigh                  float64 `json:"alphaHigh"`
	AlphaLow                   float64 `json:"alphaLow"`
	LiquidAlphaEnabled         bool    `json:"liquidAlphaEnabled"`
}

type CheckHotkey struct {
	IsHotkeyValid bool `json:"isHotkeyValid"`
}

type AccountNonce struct {
	AccountNonce int `json:"accountNonce"`
}

type ServeAxonParams struct {
	Version      int `json:"version"`
	IP           int `json:"ip"`
	Port         int `json:"port"`
	IPType       int `json:"ipType"`
	Netuid       int `json:"netuid"`
	Protocol     int `json:"protocol"`
	Placeholder1 int `json:"placeholder1"`
	Placeholder2 int `json:"placeholder2"`
}

type SetWeightsParams struct {
	Netuid     int   `json:"netuid"`
	Dests      []int `json:"dests"`
	Weights    []int `json:"weights"`
	VersionKey int   `json:"versionKey"`
}

type SetCommitRevealWeightsParams struct {
	Netuid      int    `json:"netuid"`
	Commit      string `json:"commit"`
	RevealRound int    `json:"revealRound"`
}

type SignMessageParams struct {
	Message string `json:"message"`
}

type SignMessage struct {
	Signature string `json:"signature"`
}

type VerifyMessageParams struct {
	Message       string `json:"message"`
	Signature     string `json:"signature"`
	SigneeAddress string `json:"signeeAddress"`
}

type VerifyMessage struct {
	Valid bool `json:"valid"`
}
