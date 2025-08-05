package main

import (
	"time"
)

type CodeFileObject struct {
	Filename string `json:"filename"`
	Content  string `json:"content"`
}

type CodeAnswer struct {
	Files []CodeFileObject `json:"files"`
}

type Score struct {
	RawScore                        float64 `json:"raw_score"`
	RankId                          uint8   `json:"rank_id"`
	NormalisedScore                 float64 `json:"normalised_score"`
	GroundTruthScore                float64 `json:"ground_truth_score"`
	CosineSimilarityScore           float64 `json:"cosine_similarity_score"`
	NormalisedCosineSimilarityScore float64 `json:"normalised_cosine_similarity_score"`
	CubucRewardScore                float64 `json:"cubuc_reward_score"`
}

type ScoreCriteria struct {
	Type   string `json:"type"`
	Min    string `json:"min"`
	Max    string `json:"max"`
	Scores Score  `json:"scores"`
}

type CompletionResponse struct {
	Model         string          `json:"model"`
	Completion    CodeAnswer      `json:"completion"`
	CompletionId  string          `json:"completion_id"`
	RankId        uint8           `json:"rank_id"`
	Score         float64         `json:"score"`
	CriteriaTypes []ScoreCriteria `json:"criteria_types"`
}

type TaskSynapseObject struct {
	EpochTimestamp      float64              `json:"epoch_timestamp"`
	TaskId              string               `json:"task_id"`
	PreviousTaskId      string               `json:"previous_task_id"`
	Prompt              string               `json:"prompt"`
	TaskType            string               `json:"task_type"`
	ExpireAt            time.Time            `json:"expire_at"`
	CompletionResponses []CompletionResponse `json:"completion_responses"`
	DojoTaskId          string               `json:"dojo_task_id"`
	GroundTruth         []float64            `json:"ground_truth"`
	MinerHotkey         string               `json:"miner_hotkey"`
	MinerColdkey        string               `json:"miner_coldkey"`
}
