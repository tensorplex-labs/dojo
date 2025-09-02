package taskapi

import (
	"fmt"
	"net/url"

	"github.com/bytedance/sonic"
	"github.com/go-resty/resty/v2"
	"github.com/tensorplex-labs/dojo/internal/config"
)

type TaskApiInterface interface {
	CreateCodegenTask(headers AuthHeaders, req CreateTasksRequest[CodegenTaskMetadata]) (Response[map[string]any], error)
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
func (t *TaskApi) CreateCodegenTask(headers AuthHeaders, req CreateTasksRequest[CodegenTaskMetadata]) (Response[map[string]any], error) {
	var out Response[map[string]any]
	metadataBytes, err := sonic.Marshal(req.Metadata)
	if err != nil {
		return Response[map[string]any]{}, fmt.Errorf("marshal metadata: %w", err)
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
	// Print out the header
	fmt.Printf("Creating task with headers: %+v\n", headers)

	resp, err := r.Post("/api/v1/validator/tasks")
	if err != nil {
		return Response[map[string]any]{}, fmt.Errorf("create task: %w", err)
	}
	if resp.IsError() {
		return Response[map[string]any]{}, fmt.Errorf("create task returned status %d: %s", resp.StatusCode(), resp.String())
	}
	return out, nil
}
