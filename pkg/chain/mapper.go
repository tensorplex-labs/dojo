package chain

import (
	"fmt"
	"math/big"
	"strings"

	"github.com/bytedance/sonic"
)

func (d *DividendEntry) UnmarshalJSON(data []byte) error {
	var tuple []any
	if err := sonic.Unmarshal(data, &tuple); err != nil {
		return err
	}

	if len(tuple) != 2 {
		return fmt.Errorf("expected tuple of length 2, got %d",
			len(tuple))
	}

	hotkey, ok := tuple[0].(string)
	if !ok {
		return fmt.Errorf("expected string for hotkey, got %T",
			tuple[0])
	}
	d.Hotkey = hotkey

	switch v := tuple[1].(type) {
	case float64:
		d.Amount = v
	case int:
		d.Amount = float64(v)
	default:
		return fmt.Errorf("expected number for amount, got %T",
			tuple[1])
	}

	return nil
}

// UnmarshalJSON implements custom JSON unmarshaling for HexOrInt
func (h *HexOrInt) UnmarshalJSON(data []byte) error {
	h.Value = new(big.Int)

	// Try to unmarshal as a number first
	var num uint64
	if err := sonic.Unmarshal(data, &num); err == nil {
		h.Value.SetUint64(num)
		return nil
	}

	// Try as int64 in case it's a signed number
	var signedNum int64
	if err := sonic.Unmarshal(data, &signedNum); err == nil {
		if signedNum < 0 {
			// For blockchain difficulty values, negative doesn't make sense
			return fmt.Errorf("negative values not supported for difficulty: %d", signedNum)
		}
		h.Value.SetInt64(signedNum)
		return nil
	}

	// If that fails, try as a string (could be hex or large decimal)
	var str string
	if err := sonic.Unmarshal(data, &str); err != nil {
		return fmt.Errorf("value must be a number or string, got: %s", string(data))
	}

	// Handle hex strings (with or without 0x prefix)
	if strings.HasPrefix(str, "0x") || strings.HasPrefix(str, "0X") {
		// Remove 0x prefix and parse as hex
		hexStr := strings.TrimPrefix(strings.TrimPrefix(str, "0x"), "0X")
		if _, ok := h.Value.SetString(hexStr, 16); !ok {
			return fmt.Errorf("invalid hex string: %s", str)
		}
		return nil
	}

	// Handle regular decimal strings (can be very large)
	if _, ok := h.Value.SetString(str, 10); !ok {
		return fmt.Errorf("invalid number string: %s", str)
	}
	return nil
}

// MarshalJSON implements custom JSON marshaling for HexOrInt
func (h HexOrInt) MarshalJSON() ([]byte, error) {
	if h.Value == nil {
		return sonic.Marshal(0)
	}
	// If it fits in uint64, marshal as number, otherwise as string
	if h.Value.IsUint64() {
		return sonic.Marshal(h.Value.Uint64())
	}
	// For very large numbers, marshal as decimal string
	return sonic.Marshal(h.Value.String())
}

// Int64 returns the underlying value as int64 (may overflow for very large values)
func (h HexOrInt) Int64() int64 {
	if h.Value == nil {
		return 0
	}
	return h.Value.Int64()
}

// Uint64 returns the underlying value as uint64 (may overflow for very large values)
func (h HexOrInt) Uint64() uint64 {
	if h.Value == nil {
		return 0
	}
	return h.Value.Uint64()
}

// BigInt returns the underlying big.Int value
func (h HexOrInt) BigInt() *big.Int {
	if h.Value == nil {
		return big.NewInt(0)
	}
	return new(big.Int).Set(h.Value) // Return a copy to prevent mutation
}

// String returns the decimal string representation
func (h HexOrInt) String() string {
	if h.Value == nil {
		return "0"
	}
	return h.Value.String()
}
