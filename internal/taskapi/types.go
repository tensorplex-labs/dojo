package taskapi

import "mime/multipart"

// CreateTasksRequest represents the payload to create a new task.
type CreateTasksRequest[T CodegenTaskMetadata] struct {
	TaskType  string                  `form:"task_type" json:"task_type"`
	Metadata  T                       `form:"metadata" json:"metadata"`
	Assignees []string                `form:"assignees" json:"assignees"`
	ExpireAt  string                  `form:"expire_at" json:"expire_at"`
	Files     []*multipart.FileHeader `form:"files" json:"files,omitempty"`
}

// AuthHeaders represents the authentication headers required for API requests.
type AuthHeaders struct {
	Hotkey    string `header:"X-Hotkey"`
	Signature string `header:"X-Signature"`
	Message   string `header:"X-Message"`
}

// Response represents a generic API response structure.
type Response[T CreateTaskResponse | SubmitCompletionResponse | VotesResponse | any] struct {
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

// CreateTaskResponse represents the response data for a created task.
type CreateTaskResponse struct {
	TaskID string `json:"task_id"`
}

// SubmitCompletionResponse represents the response data for a submitted completion.
type SubmitCompletionResponse struct {
	CompletionID string `json:"completion_id"`
}

// SuccessResponse represents a successful API response with data.
type SuccessResponse[T any] = Response[T]

// ErrorResponse represents an error API response without data.
type ErrorResponse = Response[struct{}]

// PaginatedResponse represents a paginated API response with data.
type PaginatedResponse[T any] = Response[T]

// CodegenTaskMetadata represents the metadata for a codegen task
type CodegenTaskMetadata struct {
	Prompt              string `json:"prompt"`
	ValidatorCompletion string `json:"validator_completion"`
}

// VotesResponse represents the response structure for votes
type VotesResponse struct {
	Votes []VoteData `json:"votes"`
}

// VoteData represents the structure of a single vote
type VoteData struct {
	ID                string `json:"id"`
	VoterHotkey       string `json:"voter_hotkey"`
	TaskID            string `json:"task_id"`
	ChoseCompletionID string `json:"chose_completion_id"`
	Weight            int64  `json:"weight"`
	Tasktype          string `json:"tasktype"`
	ValidatorHotkey   string `json:"validator_hotkey"`
	CreatedAt         string `json:"created_at"`
	ExpireAt          string `json:"expire_at"`

	UpdatedAt string `json:"updated_at"`
}
