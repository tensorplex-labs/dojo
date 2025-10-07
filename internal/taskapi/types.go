package taskapi

import (
	"mime/multipart"
	"time"
)

// CreateTasksRequest represents the payload to create a new task.
type CreateTasksRequest[T CodegenTaskMetadata] struct {
	TaskType  string                  `form:"task_type" json:"task_type"`
	Metadata  T                       `form:"metadata" json:"metadata"`
	Assignees []AssigneeData          `form:"assignees" json:"assignees"`
	ExpireAt  string                  `form:"expire_at" json:"expire_at"`
	Files     []*multipart.FileHeader `form:"files" json:"files,omitempty"`
}

type AssigneeData struct {
	Hotkey string `form:"hotkey" json:"hotkey"`
	Prompt string `form:"prompt" json:"prompt"`
	Role   string `form:"role" json:"role"`
}

// AuthHeaders represents the authentication headers required for API requests.
type AuthHeaders struct {
	Hotkey    string `header:"X-Hotkey"`
	Signature string `header:"X-Signature"`
	Message   string `header:"X-Message"`
}

// Response represents a generic API response structure.
type Response[T CreateTaskResponse | SubmitCompletionResponse | VotesResponse | TaskStatusUpdateResponse | []VotingPhaseTasksResponse | PostTaskScoresAnalyticsResponse | []PostTaskScoresAnalyticsBatchResponse | any] struct {
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
	Prompt                  string `json:"prompt"`
	ValidatorDuel           bool   `json:"validator_duel"`
	NegativeGeneratorHotkey string `json:"negative_generator_hotkey"`
}

// VotesResponse represents the response structure for votes
type VotesResponse struct {
	Tasks []VoteTaskData `json:"tasks"`
	Total int64          `json:"total"`
}

// VoteData represents the structure of a single vote
type VoteData struct {
	ID                 string  `json:"id"`
	VoterHotkey        string  `json:"voter_hotkey"`
	ChosenCompletionID string  `json:"chosen_completion_id"`
	Weight             float64 `json:"weight"`
	CreatedAt          string  `json:"created_at"`
}

// VoteTaskData represents the structure of a vote task
type VoteTaskData struct {
	ID              string           `json:"id"`
	TaskType        string           `json:"task_type"`
	ValidatorHotkey string           `json:"validator_hotkey"`
	ExpireAt        string           `json:"expire_at"`
	TaskStatus      string           `json:"task_status"`
	CreatedAt       string           `json:"created_at"`
	Completions     []VoteCompletion `json:"completions"`
	Votes           []VoteData       `json:"votes"`
}

// VoteCompletion represents a single completion within a vote task
type VoteCompletion struct {
	ID                string `json:"id"`
	ParticipantHotkey string `json:"participant_hotkey"`
}

// TaskStatusUpdateResponse represents the response data for a task status update.
type TaskStatusUpdateResponse struct {
	TaskID string `json:"task_id"`
	Status string `json:"status"`
}

// VotingPhaseTasksResponse represents tasks in the voting phase.
type VotingPhaseTasksResponse struct {
	ID        string `json:"id"`
	CreatedAt string `json:"created_at"`
	ExpireAt  string `json:"expire_at"`
}

// PostTaskScoresAnalyticsResponse represents the response data for a posted task scores analytics.
type PostTaskScoresAnalyticsResponse struct {
	ID     string `json:"id"`
	TaskID string `json:"task_id"`
}

type ScoresRecord struct {
	Hotkey  string  `json:"hotkey"`
	Coldkey string  `json:"coldkey"`
	Score   float64 `json:"score"`
	Role    string  `json:"role"`
}

type VotesRecord struct {
	VoterHotkey        string  `json:"voter_hotkey"`
	VoterColdkey       string  `json:"voter_coldkey"`
	ChosenCompletionID string  `json:"chosen_completion_id"`
	VoteWeight         float64 `json:"vote_weight"`
	VoteeHotkey        string  `json:"votee_hotkey"`
	VoteeColdkey       string  `json:"votee_coldkey"`
	VoteeRole          string  `json:"votee_role"`
}

type ScoredTaskAnalyticsRecord struct {
	TaskID            string         `json:"task_id"`
	TaskType          string         `json:"task_type"`
	CreatedAt         time.Time      `json:"created_at"`
	AnalyticsMetadata map[string]any `json:"analytics_metadata"`
	ValidatorHotkey   string         `json:"validator_hotkey"`
	ScoresRecord      []ScoresRecord `json:"scores_record"`
	VotesRecord       []VotesRecord  `json:"votes_record"`
}

type PostTaskScoresAnalyticsBatchResponse struct {
	TaskID  string `json:"task_id"`
	Status  string `json:"status"`
	Message string `json:"message"`
}
