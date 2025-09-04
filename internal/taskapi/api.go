// Package taskapi provides a simple client wrapper for the task API service.
package taskapi

import (
	"fmt"
	"net/url"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"

	"github.com/tensorplex-labs/dojo/internal/config"
)

// TaskApiInterface is the interface for the task client methods used by validator.
type TaskAPIInterface interface {
	CreateCodegenTask(
		headers AuthHeaders,
		req CreateTasksRequest[CodegenTaskMetadata],
	) (Response[CreateTaskResponse], error)
	SubmitCompletion(headers AuthHeaders, taskID string, completion string) (Response[SubmitCompletionResponse], error)
}

// TaskApi is a REST client wrapper for the task service.
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
		SetJSONUnmarshaler(sonic.Unmarshal)

	return &TaskAPI{

		cfg:    cfg,
		client: client,
	}, nil
}

// CreateCodegenTask creates a task with codegen metadata for assigned validators.
func (t *TaskAPI) CreateCodegenTask(headers AuthHeaders, req CreateTasksRequest[CodegenTaskMetadata]) (Response[CreateTaskResponse], error) { //nolint:lll
	var out Response[CreateTaskResponse]
	metadataBytes, err := sonic.Marshal(req.Metadata)
	if err != nil {
		return Response[CreateTaskResponse]{}, fmt.Errorf("marshal metadata: %w", err)

	}

	vals := url.Values{}
	vals.Set("task_type", req.TaskType)
	vals.Set("metadata", string(metadataBytes))
	for _, a := range req.Assignees {
		vals.Add("assignees", a)
	}
	vals.Set("expire_at", req.ExpireAt)

	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetFormDataFromValues(vals).
		SetResult(&out)

	resp, err := r.Post("/api/v1/validator/tasks")
	if err != nil {
		return Response[CreateTaskResponse]{}, fmt.Errorf("create task: %w", err)
	}
	if resp.IsError() {
		return Response[CreateTaskResponse]{}, fmt.Errorf("create task returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}

func (t *TaskAPI) SubmitCompletion(headers AuthHeaders, taskID string, completion string) (Response[SubmitCompletionResponse], error) {
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

	resp, err := r.Put(fmt.Sprintf("/api/v1/validator/tasks/%s/completions", taskID))
	if err != nil {
		return Response[SubmitCompletionResponse]{}, fmt.Errorf("submit completion: %w", err)
	}
	if resp.IsError() {
		return Response[SubmitCompletionResponse]{}, fmt.Errorf("submit completion returned status %d: %s",
			resp.StatusCode(), resp.String())
	}
	return out, nil
}
