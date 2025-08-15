package kami

import (
	"os"
	"strconv"
	"testing"

	"github.com/tensorplex-labs/dojo/internal/config"
)

func TestKamiIntegration_ReadOnly(t *testing.T) {
	if os.Getenv("KAMI_INTEGRATION") != "1" {
		t.Skip("KAMI_INTEGRATION!=1; skipping real Kami integration test")
	}

	host := os.Getenv("KAMI_HOST")
	if host == "" {
		host = "127.0.0.1"
	}
	port := os.Getenv("KAMI_PORT")
	if port == "" {
		port = "8080"
	}

	cfg := &config.KamiEnvConfig{KamiHost: host, KamiPort: port}
	k, err := NewKami(cfg)
	if err != nil {
		t.Fatalf("NewKami: %v", err)
	}

	lb, err := k.GetLatestBlock()
	if err != nil {
		t.Fatalf("GetLatestBlock error: %v", err)
	}
	if !lb.Success {
		t.Fatalf("GetLatestBlock not success: %+v", lb)
	}

	kr, err := k.GetKeyringPair()
	if err != nil {
		t.Fatalf("GetKeyringPair error: %v", err)
	}
	if kr.Data.KeyringPair.Address == "" {
		t.Fatalf("GetKeyringPair returned empty address: %+v", kr)
	}

	if netuidStr := os.Getenv("KAMI_NETUID"); netuidStr != "" {
		netuid, perr := strconv.Atoi(netuidStr)
		if perr == nil {
			mg, merr := k.GetMetagraph(netuid)
			if merr != nil {
				t.Fatalf("GetMetagraph error: %v", merr)
			}
			if mg.Data.Netuid != netuid {
				t.Fatalf("GetMetagraph unexpected netuid: %+v", mg)
			}
		}
	}
}
