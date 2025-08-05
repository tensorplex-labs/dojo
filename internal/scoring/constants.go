package scoring

func DefaultCubicParams() CubicParams {
	return CubicParams{
		Scaling:     0.006,
		Translation: 7.0,
		Offset:      2.0,
	}
}
