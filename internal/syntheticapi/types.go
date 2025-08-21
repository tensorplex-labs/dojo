package syntheticapi

type GenerateQuestionResponse struct {
	Success bool   `json:"success"`
	Prompt  string `json:"prompt"`
	Qa_Id   string `json:"qa_id"`
}

type GenerateAnswerResponse[T CodegenAnswer] struct {
	Success bool `json:"success"`
	Answer  T    `json:"answer"`
}
type AugmentQuestionResponse struct {
	Success  bool     `json:"success"`
	Augments []string `json:"augments"`
}

type OrderAnswerResponse struct {
	Success  bool   `json:"success"`
	AnswerID string `json:"ans_id"`
}

// ----------------------------- Codegen Types -----------------------------
type CodegenAnswer struct {
	Prompt    string            `json:"prompt"`
	Responses []CodegenResponse `json:"responses"`
}

type CodegenResponse struct {
	Model      string            `json:"model"`
	Completion CodegenCompletion `json:"completion"`
	Cid        string            `json:"cid"`
}

type CodegenCompletion struct {
	Files []CodegenFiles `json:"files"`
}

type CodegenFiles struct {
	Filename string `json:"filename"`
	Content  string `json:"content"`
}

// ----------------------------- Codegen Types -----------------------------
