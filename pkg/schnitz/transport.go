package schnitz

// Request types from messaging server
type PingRequest struct {
	Message string `json:"message" validate:"required,min=1,max=500"`
}

// Response types from messaging server
type PingResponse struct {
	Echo      string `json:"echo"`
	Timestamp int64  `json:"timestamp"`
}
