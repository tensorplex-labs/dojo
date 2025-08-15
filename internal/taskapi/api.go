package taskapi

import (
	"fmt"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/tensorplex-labs/dojo/internal/config"
)

type TaskApiInterface interface {
	CreateTask(headers AuthHeaders, req CreateTasksRequest) (Response[map[string]any], error)
}

type TaskApi struct {
	cfg    *config.TaskApiEnvConfig
	client *resty.Client
}

func NewTaskApi(cfg *config.TaskApiEnvConfig) (*TaskApi, error) {
	if cfg == nil {
		return nil, fmt.Errorf("task api env configuration cannot be nil")
	}

	client := resty.New().
		SetBaseURL(cfg.TaskApiUrl).
		SetJSONMarshaler(sonic.Marshal).
		SetJSONUnmarshaler(sonic.Unmarshal)

	return &TaskApi{
		cfg:    cfg,
		client: client,
	}, nil
}

// TODO: Possibly have a fix response type for task api!
func (t *TaskApi) CreateTask(headers AuthHeaders, req CreateTasksRequest) (Response[map[string]any], error) {
	var out Response[map[string]any]
	r := t.client.R().
		SetHeader("X-Hotkey", headers.Hotkey).
		SetHeader("X-Signature", headers.Signature).
		SetHeader("X-Message", headers.Message).
		SetFormData(map[string]string{
			"task_type": req.TaskType,
			"metadata":  req.Metadata,
			"assignee":  req.Assignee,
			"expire_at": req.ExpireAt,
		}).
		SetResult(&out)

	resp, err := r.Post("/api/v1/tasks/")
	if err != nil {
		return Response[map[string]any]{}, fmt.Errorf("create task: %w", err)
	}
	if resp.IsError() {
		return Response[map[string]any]{}, fmt.Errorf("create task returned status %d: %s", resp.StatusCode(), resp.String())
	}
	return out, nil
}
