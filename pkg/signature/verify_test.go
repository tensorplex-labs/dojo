package signature

import (
	"testing"
)

func TestSignatureVerification(t *testing.T) {
	message := "I solemnly swear that I am up to some good. Hotkey: 5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"
	signature := "0x8ee4ce50165f23b739ec55c2beeafcd273685819c32470df26b0641d15593d3b08b8aef7c391f01e7c2e34c2ee12b80df0c4b615cc0d0966be0dc81192bbc286"
	ss58Address := "5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"

	ok, err := Verify(message, signature, ss58Address)
	if err != nil {
		t.Fatalf("Verification failed: %v", err)
	}

	if !ok {
		t.Error("Expected signature to be valid, but it was not")
	}
}

func TestSignatureVerificationFail(t *testing.T) {
	t.Run("invalid signature format", func(t *testing.T) {
		message := "test message"
		invalidSignature := "8ee4ce50165f23b739ec55c2beeafcd273685819c32470df26b0641d15593d3b08b8aef7c391f01e7c2e34c2ee12b80df0c4b615cc0d0966be0dc81192bbc286" // missing 0x prefix
		ss58Address := "5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"

		ok, err := Verify(message, invalidSignature, ss58Address)
		if err == nil {
			t.Error("Expected error for signature without 0x prefix")
		}
		if ok {
			t.Error("Expected verification to fail")
		}
	})

	t.Run("invalid signature length", func(t *testing.T) {
		message := "test message"
		shortSignature := "0x8ee4ce50165f23b739ec55c2beeafcd273685819c32470df26b0641d15593d3b" // too short
		ss58Address := "5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"

		ok, err := Verify(message, shortSignature, ss58Address)
		if err == nil {
			t.Error("Expected error for short signature")
		}
		if ok {
			t.Error("Expected verification to fail")
		}
	})

	t.Run("invalid SS58 address", func(t *testing.T) {
		message := "test message"
		signatureHex := "0x8ee4ce50165f23b739ec55c2beeafcd273685819c32470df26b0641d15593d3b08b8aef7c391f01e7c2e34c2ee12b80df0c4b615cc0d0966be0dc81192bbc286"
		ss58Address := "invalid-address"

		ok, err := Verify(message, signatureHex, ss58Address)
		if err == nil {
			t.Error("Expected error for invalid SS58 address")
		}
		if ok {
			t.Error("Expected verification to fail")
		}
	})
}
