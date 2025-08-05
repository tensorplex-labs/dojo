package main

import (
	"fmt"
	"os"
	"time"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/rs/zerolog/pkgerrors"
	schnitz "github.com/tensorplex-labs/dojo/pkg/schnitz"
)

const (
	baseURL = "http://localhost:8888"
	// message   = "I solemnly swear that I am up to some good. Hotkey: 5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"
	// signature = "0x8ee4ce50165f23b739ec55c2beeafcd273685819c32470df26b0641d15593d3b08b8aef7c391f01e7c2e34c2ee12b80df0c4b615cc0d0966be0dc81192bbc286"
	// hotkey    = "5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"
)

type UserRequest struct {
	Name  string `json:"name"`
	Email string `json:"email"`
}

func main() {
	log.Info().Msg("Starting client example...")
	// Configure zerolog for human-readable output
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})
	zerolog.ErrorStackMarshaler = pkgerrors.MarshalStack
	err := godotenv.Load()
	if err != nil {
		log.Fatal().Msg("Error loading .env file")
	}

	// // Create authentication parameters
	// authParams := schnitz.AuthParams{
	// 	Hotkey:    hotkey,
	// 	Message:   message,
	// 	Signature: signature,
	// }

	fmt.Println("\n=== Example: Client with Compression ===")
	client, err := schnitz.NewClient(&schnitz.ClientConfig{
		Timeout:         10 * time.Second,
		ZstdCompression: true,
	})
	if err != nil {
		log.Fatal().Err(err).Msg("Failed to create compressed client")
	}
	defer client.Close()

	fmt.Println("\n=== Example: Generic Requests ===")

	// Create user request
	userReq := UserRequest{
		Name:  "John Doe",
		Email: "john@example.com",
	}
	var userResp UserRequest

	authParams, err := client.CreateAuthParams()
	if err != nil {
		log.Error().Err(err).Msg("Failed to create auth params")
		return
	}

	err = client.Send(baseURL, userReq, &userResp, authParams)
	if err != nil {
		log.Error().Err(err).Msg("UserRequest failed")
	} else {
		fmt.Printf("User response: Name=%s, Email=%s\n", userResp.Name, userResp.Email)
	}

	fmt.Println("\n=== Example: Error Handling ===")

	// Test with invalid data
	invalidUserReq := UserRequest{
		Name:  "",
		Email: "test@example.com",
	}
	var invalidUserResp UserRequest

	err = client.Send(
		baseURL,
		invalidUserReq,
		&invalidUserResp,
		authParams,
	)
	if err != nil {
		fmt.Printf("Expected error for empty name: %v\n", err)
	} else {
		fmt.Printf("Unexpected success: %+v\n", invalidUserResp)
	}

	urls := make([]string, 5)
	requests := make([]UserRequest, 5)
	responses := make([]*UserRequest, 5)
	for i := 0; i < 5; i++ {
		urls[i] = baseURL
		request := UserRequest{
			Name:  fmt.Sprintf("User %d", i),
			Email: "abc@gmail.com",
		}
		requests[i] = request
		responses[i] = &UserRequest{} // Use pointer to allow unmarshalling into the response
	}

	log.Info().Msg("Sending multiple requests...")
	_ = schnitz.SendMany(client, urls, requests, responses, authParams)

	log.Info().Msg("Finished sending multiple requests...")

	fmt.Println("\n=== Client Example Complete ===")
}
