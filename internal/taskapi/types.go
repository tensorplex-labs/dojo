package taskapi

import "mime/multipart"

// ------------- Generic Types -------------//
type CreateTasksRequest[T CodegenTaskMetadata] struct {
	TaskType  string                  `form:"task_type" json:"task_type"`
	Metadata  T                       `form:"metadata" json:"metadata"`
	Assignees []string                `form:"assignees" json:"assignees"`
	ExpireAt  string                  `form:"expire_at" json:"expire_at"`
	Files     []*multipart.FileHeader `form:"files" json:"files,omitempty"`
}

type AuthHeaders struct {
	Hotkey    string `header:"X-Hotkey"`
	Signature string `header:"X-Signature"`
	Message   string `header:"X-Message"`
}

type Response[T CreateTaskResponse | SubmitCompletionResponse | any] struct {
	Success    bool   `json:"success"`
	Message    string `json:"message,omitempty"`
	Error      string `json:"error,omitempty"`
	Code       int    `json:"code,omitempty"`
	Data       T      `json:"data,omitempty"`
	Page       int    `json:"page,omitempty"`
	PageSize   int    `json:"page_size,omitempty"`
	TotalPages int    `json:"total_pages,omitempty"`
	TotalItems int64  `json:"total_items,omitempty"`
}

type CreateTaskResponse struct {
	TaskID string `json:"task_id"`
}

type SubmitCompletionResponse struct {
	CompletionID string `json:"completion_id"`
}

type SuccessResponse[T any] = Response[T]

type ErrorResponse = Response[struct{}]

type PaginatedResponse[T any] = Response[T]

// ------------- Task Types -------------//

// CodegenTaskMetadata represents the metadata for a codegen task
type CodegenTaskMetadata struct {
	Prompt              string `json:"prompt"`
	ValidatorCompletion string `json:"validator_completion"`
}
