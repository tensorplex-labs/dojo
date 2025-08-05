# Scoring Module

## Usage

Refer to cmd/scoring/main.go for actual usage.

## Future / TODOs

- Scoring Pipeline to be even more modular

```go
pipeline1 = scoring.NewScoringPipeline(
GroundTruthPipeline{
    withGroundTruth(False) // Or True
},

RawScoreProcessingPipeline{
l1normalize (0,1)
minmax()
cubic()
transform()
scale()
}

)

pipeline2 = scoring.NewScoringPipeline(
GroundTruthPipeline{
    withGroundTruth(True) // Or True
},

RawScoreProcessingPipeline{
l1normalize (0,1)
minmax()
cosineSimilairty()
scale()
cubic()
transform()
scale()
}

)

```

- maybe move the math operations into a utils folder
