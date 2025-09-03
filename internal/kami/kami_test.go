package kami

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/tensorplex-labs/dojo/internal/config"
)

func newTestServer(t *testing.T, handler http.HandlerFunc) (*httptest.Server, *Kami) {
	ts := httptest.NewServer(handler)
	t.Cleanup(ts.Close)

	kc := &config.KamiEnvConfig{
		KamiHost: ts.Listener.Addr().(*net.TCPAddr).IP.String(),
		KamiPort: fmt.Sprint(ts.Listener.Addr().(*net.TCPAddr).Port),
	}
	k, err := NewKami(kc)
	if err != nil {
		t.Fatalf("new kami: %v", err)
	}
	k.BaseURL = ts.URL
	k.client.SetBaseURL(ts.URL)
	return ts, k
}

func TestNewKami_NilConfig(t *testing.T) {
	_, err := NewKami(nil)
	if err == nil {
		t.Fatalf("expected error when cfg is nil")
	}
}

func TestServeAxon_Success(t *testing.T) {
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chain/serve-axon" || r.Method != http.MethodPost {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"statusCode":200,"success":true,"data":"0xabc","error":null}`))
	})

	res, err := k.ServeAxon(ServeAxonParams{})
	if err != nil {
		t.Fatalf("ServeAxon error: %v", err)
	}
	if res.Data != "0xabc" || !res.Success {
		t.Fatalf("unexpected response: %+v", res)
	}
}

func TestServeAxon_HTTPError(t *testing.T) {
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte("bad"))
	})
	_, err := k.ServeAxon(ServeAxonParams{})
	if err == nil {
		t.Fatalf("expected error")
	}
}

func TestServeAxon_ResponseErrorField(t *testing.T) {
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"statusCode":200,"success":false,"data":"","error":{"msg":"boom"}}`))
	})
	_, err := k.ServeAxon(ServeAxonParams{})
	if err == nil {
		t.Fatalf("expected error")
	}
}

func TestGetMetagraph_Success(t *testing.T) {
	payload := `{"statusCode":200,"success":true,"data":{"netuid":1,"name":"n","symbol":"s","identity":{"subnetName":"","githubRepo":"","subnetContact":"","subnetUrl":"","discord":"","description":"","additional":""},"networkRegisteredAt":0,"ownerHotkey":"","ownerColdkey":"","block":0,"tempo":0,"lastStep":0,"blocksSinceLastStep":0,"subnetEmission":0,"alphaIn":0,"alphaOut":0,"taoIn":0,"alphaOutEmission":0,"alphaInEmission":0,"taoInEmission":0,"pendingAlphaEmission":0,"pendingRootEmission":0,"subnetVolume":0,"movingPrice":{"bits":0},"rho":0,"kappa":0,"minAllowedWeights":0,"maxAllowedWeights":0,"weightsVersion":0,"weightsRateLimit":0,"activityCutoff":0,"maxValidators":0,"numUids":0,"maxUids":0,"burn":0,"difficulty":0,"registrationAllowed":false,"powRegistrationAllowed":false,"immunityPeriod":0,"minDifficulty":"0x0","maxDifficulty":"0x0","minBurn":0,"maxBurn":0,"adjustmentAlpha":"0x0","adjustmentInterval":0,"targetRegsPerInterval":0,"maxRegsPerBlock":0,"servingRateLimit":0,"commitRevealWeightsEnabled":false,"commitRevealPeriod":0,"liquidAlphaEnabled":false,"alphaHigh":0,"alphaLow":0,"bondsMovingAvg":0,"hotkeys":[],"coldkeys":[],"identities":[],"axons":[],"active":[],"validatorPermit":[],"pruningScore":[],"lastUpdate":[],"emission":[],"dividends":[],"incentives":[],"consensus":[],"trust":[],"rank":[],"blockAtRegistration":[],"alphaStake":[],"taoStake":[],"totalStake":[],"taoDividendsPerHotkey":[],"alphaDividendsPerHotkey":[]},"error":null}`
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chain/subnet-metagraph/1" || r.Method != http.MethodGet {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(payload))
	})

	res, err := k.GetMetagraph(1)
	if err != nil {
		t.Fatalf("GetMetagraph error: %v", err)
	}
	if res.Data.Netuid != 1 {
		t.Fatalf("unexpected response: %+v", res)
	}
}

func TestGetLatestBlock_Success(t *testing.T) {
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chain/latest-block" || r.Method != http.MethodGet {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"statusCode":200,"success":true,"data":{"parentHash":"0x1","blockNumber":1,"stateRoot":"0x2","extrinsicsRoot":"0x3"},"error":null}`))
	})

	res, err := k.GetLatestBlock()
	if err != nil {
		t.Fatalf("GetLatestBlock error: %v", err)
	}
	if res.Data.BlockNumber != 1 {
		t.Fatalf("unexpected response: %+v", res)
	}
}

func TestSetWeights_Success(t *testing.T) {
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chain/set-weights" || r.Method != http.MethodPost {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"statusCode":200,"success":true,"data":"0xdead","error":null}`))
	})

	res, err := k.SetWeights(SetWeightsParams{Netuid: 1})
	if err != nil {
		t.Fatalf("SetWeights error: %v", err)
	}
	if res.Data != "0xdead" {
		t.Fatalf("unexpected response: %+v", res)
	}
}

func TestSignVerifyAndKeyring_Success(t *testing.T) {
	_, k := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/substrate/sign-message/sign":
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"statusCode":200,"success":true,"data":{"signature":"sig"},"error":null}`))
		case "/substrate/sign-message/verify":
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"statusCode":200,"success":true,"data":{"valid":true},"error":null}`))
		case "/substrate/keyring-pair-info":
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"statusCode":200,"success":true,"data":{"keyringPair":{"address":"addr","addressRaw":{},"isLocked":false,"meta":{},"publicKey":{},"type":"sr25519"},"walletColdkey":"cold"},"error":null}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})

	sig, err := k.SignMessage(SignMessageParams{Message: "m"})
	if err != nil || sig.Data.Signature != "sig" {
		t.Fatalf("sign unexpected: %v %+v", err, sig)
	}
	ver, err := k.VerifyMessage(VerifyMessageParams{Message: "m", Signature: "s", SigneeAddress: "a"})
	if err != nil || !ver.Data.Valid {
		t.Fatalf("verify unexpected: %v %+v", err, ver)
	}
	kr, err := k.GetKeyringPair()
	if err != nil || kr.Data.KeyringPair.Address != "addr" {
		t.Fatalf("keyring unexpected: %v %+v", err, kr)
	}
}
