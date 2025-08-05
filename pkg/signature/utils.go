package signature

import (
	"github.com/ChainSafe/gossamer/lib/crypto/sr25519"
	"github.com/vedhavyas/go-subkey"
)

func ToSs58Address(keypair *sr25519.Keypair) string {
	ss58Address := subkey.SS58Encode(
		keypair.Public().Encode(),
		SubstrateNetworkId,
	)
	return ss58Address
}
