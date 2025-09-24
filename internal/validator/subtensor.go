package validator

type SubtensorClient interface {
	GetMetagraph(netuid int) (SubnetMetagraphResponse, error)
	GetLatestBlock() (LatestBlockResponse, error)
	GetSubnetHyperparams(netuid int) (SubnetHyperparamsResponse, error)
	SetWeights(params SetWeightsParams) (ExtrinsicHashResponse, error)
	SetTimelockedWeights(params SetTimelockedWeightsParams) (ExtrinsicHashResponse, error)
	SignMessage(params SignMessageParams) (SignMessageResponse, error)
	GetKeyringPair() (KeyringPairInfoResponse, error) // Added for initialization
}

type SubtensorResponse[T any] struct {
	StatusCode int            `json:"statusCode"`
	Success    bool           `json:"success"`
	Data       T              `json:"data"`
	Error      map[string]any `json:"error"`
}

type (
	SubnetMetagraphResponse   = SubtensorResponse[SubnetMetagraph]
	LatestBlockResponse       = SubtensorResponse[LatestBlock]
	KeyringPairInfoResponse   = SubtensorResponse[KeyringPairInfo]
	SubnetHyperparamsResponse = SubtensorResponse[SubnetHyperparams]
	CheckHotkeyResponse       = SubtensorResponse[CheckHotkey]
	AccountNonceResponse      = SubtensorResponse[AccountNonce]
	SignMessageResponse       = SubtensorResponse[SignMessage]
	VerifyMessageResponse     = SubtensorResponse[VerifyMessage]
	ExtrinsicHashResponse     = SubtensorResponse[string]
)

type SubnetMetagraph struct {
	Netuid                     int            `json:"netuid"`
	Name                       string         `json:"name"`
	Symbol                     string         `json:"symbol"`
	Identity                   SubnetIdentity `json:"identity"`
	NetworkRegisteredAt        int            `json:"networkRegisteredAt"`
	OwnerHotkey                string         `json:"ownerHotkey"`
	OwnerColdkey               string         `json:"ownerColdkey"`
	Block                      int            `json:"block"`
	Tempo                      int            `json:"tempo"`
	SubnetEmission             float64        `json:"subnetEmission"`
	AlphaIn                    float64        `json:"alphaIn"`
	AlphaOut                   float64        `json:"alphaOut"`
	TaoIn                      float64        `json:"taoIn"`
	AlphaOutEmission           float64        `json:"alphaOutEmission"`
	AlphaInEmission            float64        `json:"alphaInEmission"`
	TaoInEmission              float64        `json:"taoInEmission"`
	Rho                        float64        `json:"rho"`
	Kappa                      float64        `json:"kappa"`
	WeightsVersion             int            `json:"weightsVersion"`
	WeightsRateLimit           int            `json:"weightsRateLimit"`
	MaxValidators              int            `json:"maxValidators"`
	NumUids                    int            `json:"numUids"`
	MaxUids                    int            `json:"maxUids"`
	Burn                       float64        `json:"burn"`
	RegistrationAllowed        bool           `json:"registrationAllowed"`
	PowRegistrationAllowed     bool           `json:"powRegistrationAllowed"`
	ImmunityPeriod             int            `json:"immunityPeriod"`
	TargetRegsPerInterval      int            `json:"targetRegsPerInterval"`
	MaxRegsPerBlock            int            `json:"maxRegsPerBlock"`
	CommitRevealWeightsEnabled bool           `json:"commitRevealWeightsEnabled"`
	CommitRevealPeriod         int            `json:"commitRevealPeriod"`
	LiquidAlphaEnabled         bool           `json:"liquidAlphaEnabled"`
	Hotkeys                    []string       `json:"hotkeys"`
	Coldkeys                   []string       `json:"coldkeys"`
	Axons                      []AxonInfo     `json:"axons"`
	Active                     []bool         `json:"active"`
	LastUpdate                 []int          `json:"lastUpdate"`
	AlphaStake                 []float64      `json:"alphaStake"`
	TaoStake                   []float64      `json:"taoStake"`
	TotalStake                 []float64      `json:"totalStake"`
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
	ImmunityPeriod             int  `json:"immunityPeriod"`
	Tempo                      int  `json:"tempo"`
	WeightsVersion             int  `json:"weightsVersion"`
	WeightsRateLimit           int  `json:"weightsRateLimit"`
	RegistrationAllowed        bool `json:"registrationAllowed"`
	TargetRegsPerInterval      int  `json:"targetRegsPerInterval"`
	MaxRegsPerBlock            int  `json:"maxRegsPerBlock"`
	MaxValidators              int  `json:"maxValidators"`
	CommitRevealPeriod         int  `json:"commitRevealPeriod"`
	CommitRevealWeightsEnabled bool `json:"commitRevealWeightsEnabled"`
	LiquidAlphaEnabled         bool `json:"liquidAlphaEnabled"`
}

type CheckHotkey struct {
	IsHotkeyValid bool `json:"isHotkeyValid"`
}

type AccountNonce struct {
	AccountNonce int `json:"accountNonce"`
}

type SetWeightsParams struct {
	Netuid     int   `json:"netuid"`
	Dests      []int `json:"dests"`
	Weights    []int `json:"weights"`
	VersionKey int   `json:"versionKey"`
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

type SetTimelockedWeightsParams struct {
	Netuid              int    `json:"netuid"`
	Commit              string `json:"commit"`
	RevealRound         int    `json:"revealRound"`
	CommitRevealVersion int    `json:"commitRevealVersion"`
}
