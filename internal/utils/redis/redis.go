package redis

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/rueidis"
	"github.com/tensorplex-labs/dojo/internal/config"
)

type Redis struct {
	client rueidis.Client
	cfg    *config.RedisEnvConfig
}

type RedisInterface interface {
	Get(ctx context.Context, key string) (string, error)
	GetMulti(ctx context.Context, keys []string) (map[string]string, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
	SetMulti(ctx context.Context, kv map[string]string) error
}

func NewRedis(cfg *config.RedisEnvConfig) (*Redis, error) {
	client, err := rueidis.NewClient(rueidis.ClientOption{
		InitAddress: []string{fmt.Sprintf("%s:%d", cfg.RedisHost, cfg.RedisPort)},
		Password:    cfg.RedisPassword,
	})
	if err != nil {
		return nil, err
	}

	return &Redis{
		client: client,
		cfg:    cfg,
	}, nil
}

func (r *Redis) Get(ctx context.Context, key string) (string, error) {
	resp := r.client.Do(ctx, r.client.B().Get().Key(key).Build())
	if err := resp.Error(); err != nil {
		if rueidis.IsRedisNil(err) {
			return "", nil
		}
		return "", err
	}
	return resp.ToString()
}

func (r *Redis) GetMulti(ctx context.Context, keys []string) (map[string]string, error) {
	if len(keys) == 0 {
		return map[string]string{}, nil
	}
	res := r.client.Do(ctx, r.client.B().Mget().Key(keys...).Build())
	vals, err := res.AsStrSlice()
	if err != nil {
		if rueidis.IsRedisNil(err) {
			m := make(map[string]string, len(keys))
			for _, k := range keys {
				m[k] = ""
			}
			return m, nil
		}
		return nil, err
	}
	m := make(map[string]string, len(keys))
	for i, k := range keys {
		if i < len(vals) {
			m[k] = vals[i]
		} else {
			m[k] = ""
		}
	}
	return m, nil
}

func (r *Redis) Set(ctx context.Context, key string, value string, ttl time.Duration) error {
	if ttl > 0 {
		return r.client.Do(ctx, r.client.B().Set().Key(key).Value(value).Ex(ttl).Build()).Error()
	}
	return r.client.Do(ctx, r.client.B().Set().Key(key).Value(value).Build()).Error()
}

func (r *Redis) SetMulti(ctx context.Context, kv map[string]string) error {
	if len(kv) == 0 {
		return nil
	}
	cmds := make(rueidis.Commands, 0, len(kv))
	for k, v := range kv {
		cmds = append(cmds, r.client.B().Set().Key(k).Value(v).Build())
	}
	for _, resp := range r.client.DoMulti(ctx, cmds...) {
		if err := resp.Error(); err != nil && !rueidis.IsRedisNil(err) {
			return err
		}
	}
	return nil
}
