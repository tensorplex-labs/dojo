package scoring

import (
	"github.com/tensorplex-labs/dojo/internal/utils/logger"
	"gonum.org/v1/gonum/mat"
)

type CubicParams struct {
	Scaling     float64
	Translation float64
	Offset      float64
}

type ScoringPipeline struct {
	CubicParams CubicParams
}

type ScoringPipelineOption func(*ScoringPipeline)

func WithScaling(scaling float64) ScoringPipelineOption {
	return func(p *ScoringPipeline) {
		p.CubicParams.Scaling = scaling
	}
}

func WithTranslation(translation float64) ScoringPipelineOption {
	return func(p *ScoringPipeline) {
		p.CubicParams.Translation = translation
	}
}

func WithOffset(offset float64) ScoringPipelineOption {
	return func(p *ScoringPipeline) {
		p.CubicParams.Offset = offset
	}
}

func WithCubicParams(params CubicParams) ScoringPipelineOption {
	return func(p *ScoringPipeline) {
		p.CubicParams = params
	}
}

func CubicScoringPipeline(opts ...ScoringPipelineOption) *ScoringPipeline {
	p := &ScoringPipeline{
		CubicParams: DefaultCubicParams(),
	}

	for _, opt := range opts {
		opt(p)
	}

	return p
}

func (p *ScoringPipeline) Process(rawScores *mat.Dense, groundTruth GroundTruthRank) ProcessedMinerScoreMatrix {
	logger.Sugar().Infow("Processing with cubic params", "cubicParams", p.CubicParams)
	return ProcessMinerRawScoresWithGroundTruth(rawScores, groundTruth, p.CubicParams)
}
