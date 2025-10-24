// Package taskapi provides a simple client wrapper for the task API service.
package taskapi

import (
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"

	"github.com/tensorplex-labs/dojo/internal/config"
)

// TaskAPIInterface is the interface for the task client methods used by validator.
type TaskAPIInterface interface {
	// POST requests
	CreateCodegenTask(
		headers AuthHeaders,
		req CreateTasksRequest[CodegenTaskMetadata],
		validatorCompletion string,
	) (Response[CreateTaskResponse], error)
	SubmitCompletion(headers AuthHeaders, taskID, completion string) (Response[SubmitCompletionResponse], error)
	PostTaskScoresAnalytics(headers AuthHeaders, scoredTaskAnalyticsRecord *ScoredTaskAnalyticsRecord) (Response[PostTaskScoresAnalyticsResponse], error)
	PostTaskScoresAnalyticsBatch(headers AuthHeaders, scoredTaskAnalyticsRecords ScoredTaskAnalyticsBatchRequest) (Response[PostTaskScoresAnalyticsBatchResponse], error)
	UpdateTaskToPvV(headers AuthHeaders, taskID, completion, taskMetadata string) (Response[UpdateTaskToPvVResponse], error)

	// GET requests
	GetExpiredTasks(headers AuthHeaders) (Response[VotesResponse], error)
	GetExpiredTasksRollingWindow(headers AuthHeaders, hours int) (Response[VotesResponse], error)
	GetVotingTasks(headers AuthHeaders) (Response[[]VotingPhaseTasksResponse], error)
	UpdateTaskStatus(headers AuthHeaders, taskID, status string) (Response[TaskStatusUpdateResponse], error)
	GetExpiredTasksWithOneCompletion(headers AuthHeaders) (Response[ExpiredTasksWithOneCompletionResponse], error)
}

// TaskAPI is a REST client wrapper for the task service.
type TaskAPI struct {
	cfg    *config.TaskAPIEnvConfig
	client *resty.Client
}

// NewTaskAPI constructs a new TaskAPI client.
func NewTaskAPI(cfg *config.TaskAPIEnvConfig) (*TaskAPI, error) {
	if cfg == nil {
		return nil, fmt.Errorf("task api env configuration cannot be nil")
	}

	client := resty.New().
		SetBaseURL(cfg.TaskAPIUrl).
		SetJSONMarshaler(sonic.Marshal).
		SetJSONUnmarshaler(sonic.Unmarshal).
		SetTimeout(15 * time.Second)

	return &TaskAPI{
		cfg:    cfg,
		client: client,
	}, nil
}

// CreateCodegenTask creates a task with codegen metadata for assigned validators.
func (t *TaskAPI) CreateCodegenTask(headers AuthHeaders, req CreateTasksRequest[CodegenTaskMetadata], validatorCompletion string) (Response[CreateTaskResponse], error) { //nolint:lll
	var out Response[CreateTaskResponse]

	metadataBytes, err := sonic.Marshal(req.Metadata)
	if err != nil {
		return Response[CreateTaskResponse]{}, fmt.Errorf("marshal metadata: %w", err)
	}

	vals := url.Values{}
	vals.Set("task_type", req.TaskType)
	vals.Set("metadata", string(metadataBytes))

	for _, assignee := range req.Assignees {
		var assigneeBytes []byte
		assigneeBytes, err = sonic.Marshal(assignee)
		if err != nil {
			return Response[CreateTaskResponse]{}, fmt.Errorf("marshal assignee: %w", err)
		}

		vals.Add("assignees", string(assigneeBytes))
	}

	vals.Set("expire_at", req.ExpireAt)

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetFormDataFromValues(vals).
		SetResult(&out)

	if validatorCompletion != "" {
		r.SetFileReader("files", "index.html", strings.NewReader(validatorCompletion))
	}

	resp, err := r.Post("/validator/tasks")
	if err != nil {
		return Response[CreateTaskResponse]{}, fmt.Errorf("create task: %w", err)
	}
	if resp.IsError() {
		return Response[CreateTaskResponse]{}, fmt.Errorf("create task returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}

func (t *TaskAPI) SubmitCompletion(headers AuthHeaders, taskID, completion string) (Response[SubmitCompletionResponse], error) {
	var out Response[SubmitCompletionResponse]

	metadataBytes, err := sonic.Marshal(completion)
	if err != nil {
		return Response[SubmitCompletionResponse]{}, fmt.Errorf("marshal completion: %w", err)
	}

	vals := url.Values{}
	vals.Set("metadata", string(metadataBytes))

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetFormDataFromValues(vals).
		SetResult(&out)

	resp, err := r.Put(fmt.Sprintf("/validator/tasks/%s/completions", taskID))
	if err != nil {
		return Response[SubmitCompletionResponse]{}, fmt.Errorf("submit completion: %w", err)
	}
	if resp.IsError() {
		return Response[SubmitCompletionResponse]{}, fmt.Errorf("submit completion returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}

func (t *TaskAPI) PostTaskScoresAnalytics(headers AuthHeaders, scoredTaskAnalyticsRecord *ScoredTaskAnalyticsRecord) (Response[PostTaskScoresAnalyticsResponse], error) {
	var out Response[PostTaskScoresAnalyticsResponse]

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetBody(scoredTaskAnalyticsRecord).
		SetResult(&out)

	resp, err := r.Post("/validator/analytics")
	if err != nil {
		return Response[PostTaskScoresAnalyticsResponse]{}, fmt.Errorf("post task scores analytics: %w", err)
	}
	if resp.IsError() {
		return Response[PostTaskScoresAnalyticsResponse]{}, fmt.Errorf("post task scores analytics returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}

func (t *TaskAPI) PostTaskScoresAnalyticsBatch(headers AuthHeaders, scoredTaskAnalyticsRecord ScoredTaskAnalyticsBatchRequest) (Response[PostTaskScoresAnalyticsBatchResponse], error) {
	var out Response[PostTaskScoresAnalyticsBatchResponse]

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetBody(scoredTaskAnalyticsRecord).
		SetResult(&out)

	resp, err := r.Post("/validator/analytics/batch")
	if err != nil {
		return Response[PostTaskScoresAnalyticsBatchResponse]{}, fmt.Errorf("post task scores analytics batch: %w", err)
	}
	if resp.IsError() {
		return Response[PostTaskScoresAnalyticsBatchResponse]{}, fmt.Errorf("post task scores analytics batch returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}

func (t *TaskAPI) GetExpiredTasks(headers AuthHeaders) (Response[VotesResponse], error) {
	var out Response[VotesResponse]
	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetResult(&out)

	resp, err := r.Get("/validator/tasks/expired")
	if err != nil {
		return Response[VotesResponse]{}, fmt.Errorf("get expired tasks: %w", err)
	}

	if resp.IsError() {
		return Response[VotesResponse]{}, fmt.Errorf("get expired tasks returned status %d: %s",
			resp.StatusCode(), resp.String())
	}

	return out, nil
}

func (t *TaskAPI) GetExpiredTasksRollingWindow(headers AuthHeaders, hours int) (Response[VotesResponse], error) {
	var out Response[VotesResponse]
	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetResult(&out)

	resp, err := r.Get(fmt.Sprintf("/validator/tasks/expired?hours=%d", hours))
	if err != nil {
		return Response[VotesResponse]{}, fmt.Errorf("get expired tasks for a rolling window of %d hours: %w", hours, err)
	}

	if resp.IsError() {
		return Response[VotesResponse]{}, fmt.Errorf("get expired tasks for a rolling window of %d hours returned status %d: %s", hours,
			resp.StatusCode(), resp.String())
	}

	return out, nil
}

func (t *TaskAPI) UpdateTaskStatus(headers AuthHeaders, taskID, status string) (Response[TaskStatusUpdateResponse], error) {
	var out Response[TaskStatusUpdateResponse]

	vals := url.Values{}
	vals.Set("status", status)

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetFormDataFromValues(vals).
		SetResult(&out)

	resp, err := r.Put(fmt.Sprintf("/validator/tasks/%s/status", taskID))
	if err != nil {
		return Response[TaskStatusUpdateResponse]{}, fmt.Errorf("update task status: %w", err)
	}
	if resp.IsError() {
		return Response[TaskStatusUpdateResponse]{}, fmt.Errorf("update task status returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}

func (t *TaskAPI) GetVotingTasks(headers AuthHeaders) (Response[[]VotingPhaseTasksResponse], error) {
	var out Response[[]VotingPhaseTasksResponse]
	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetResult(&out)

	resp, err := r.Get("/validator/tasks/voting")
	if err != nil {
		return Response[[]VotingPhaseTasksResponse]{}, fmt.Errorf("get voting tasks: %w", err)
	}

	if resp.IsError() {
		return Response[[]VotingPhaseTasksResponse]{}, fmt.Errorf("get voting tasks returned status %d: %s",
			resp.StatusCode(), resp.String())
	}

	return out, nil
}

func (t *TaskAPI) GetExpiredTasksWithOneCompletion(headers AuthHeaders) (Response[ExpiredTasksWithOneCompletionResponse], error) {
	var out Response[ExpiredTasksWithOneCompletionResponse]
	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetResult(&out)

	resp, err := r.Get("/validator/tasks/incomplete-pvp")
	if err != nil {
		return Response[ExpiredTasksWithOneCompletionResponse]{}, fmt.Errorf("get expired pvp/trap tasks with one missing completion: %w", err)
	}

	if resp.IsError() {
		return Response[ExpiredTasksWithOneCompletionResponse]{}, fmt.Errorf("get expired pvp/trap tasks with one missing completion returned status %d: %s",
			resp.StatusCode(), resp.String())
	}

	return out, nil
}

func (t *TaskAPI) UpdateTaskToPvV(headers AuthHeaders, taskID, completion, taskMetadata string) (Response[UpdateTaskToPvVResponse], error) {
	var out Response[UpdateTaskToPvVResponse]

	vals := url.Values{}
	vals.Set("metadata", taskMetadata)

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetFormDataFromValues(vals).
		SetResult(&out)

	if completion != "" {
		r.SetFileReader("files", "index.html", strings.NewReader(completion))
	}

	resp, err := r.Put(fmt.Sprintf("/validator/tasks/%s/completion-pvv", taskID))
	if err != nil {
		return Response[UpdateTaskToPvVResponse]{}, fmt.Errorf("update pvp/trap tasks with one missing completion to pvv: %w", err)
	}
	if resp.IsError() {
		return Response[UpdateTaskToPvVResponse]{}, fmt.Errorf("update pvp/trap tasks with one missing completion to pvv returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}
