// Package syntheticapi defines request/response types used by the synthetic service.
package syntheticapi

// GenerateQuestionResponse is the response for a generated question.
type GenerateQuestionResponse struct {
	Success  bool   `json:"success"`
	Prompt   string `json:"prompt"`
	QaID     string `json:"qa_id"`
	AnsAugID string `json:"ans_aug_id"`
}

// GenerateAnswerResponse is the response for a codegen answer.
type GenerateAnswerResponse[T CodegenAnswer] struct {
	Success bool `json:"success"`
	Answer  T    `json:"answer"`
}

// AugmentQuestionResponse contains augmented IDs for a base question.
type AugmentQuestionResponse struct {
	Success  bool     `json:"success"`
	Augments []string `json:"augments"`
}

// OrderAnswerResponse contains the ordered answer ID.
type OrderAnswerResponse struct {
	Success  bool   `json:"success"`
	AnswerID string `json:"ans_id"`
}

// ----------------------------- Codegen Types -----------------------------

// CodegenAnswer is the top-level answer payload for codegen tasks.
type CodegenAnswer struct {
	Prompt    string            `json:"prompt"`
	Responses []CodegenResponse `json:"responses"`
}

// CodegenResponse represents one response from a model.
type CodegenResponse struct {
	Model      string            `json:"model"`
	Completion CodegenCompletion `json:"completion"`
	Cid        string            `json:"cid"`
}

// CodegenCompletion includes the generated files bundle.
type CodegenCompletion struct {
	Files []CodegenFiles `json:"files"`
}

// CodegenFiles describes a single generated file.
type CodegenFiles struct {
	Filename string `json:"filename"`
	Content  string `json:"content"`
}
