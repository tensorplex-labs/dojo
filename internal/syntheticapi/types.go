package syntheticapi

type GenerateQuestionResponse struct {
	Success bool `json:"success"`
	Prompt string `json:"prompt"`
	Qa_Id string `json:"qa_id"`
}

type GenerateAnswerResponse struct {
	Success bool `json:"success"`
	Answer string `json:"answer"`
}

type AugmentQuestionResponse struct {
	Success bool `json:"success"`
	Augments []string `json:"augments"`
}
