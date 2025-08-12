package chainutils

import (
	"encoding/binary"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/rs/zerolog/log"
)

// GetExternalIP queries a public IP service and returns the external IPv4 address as net.IP
func GetExternalIP() (net.IP, error) {
	client := http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get("https://api.ipify.org")
	if err != nil {
		log.Error().Err(err).Msg("failed to query external IP")
		return nil, fmt.Errorf("query external ip: %w", err)
	}
	defer resp.Body.Close()

	buf := make([]byte, 64)
	n, err := resp.Body.Read(buf)
	if err != nil && err.Error() != "EOF" {
		log.Error().Err(err).Msg("failed to read ip response")
		return nil, fmt.Errorf("read ip response: %w", err)
	}

	ipStr := string(buf[:n])
	ip := net.ParseIP(ipStr)
	if ip == nil {
		return nil, fmt.Errorf("invalid ip returned: %s", ipStr)
	}
	ip = ip.To4()
	if ip == nil {
		return nil, fmt.Errorf("non-ipv4 address returned: %s", ipStr)
	}

	return ip, nil
}

// IPv4ToInt converts an IPv4 net.IP to its uint32 representation (big-endian)
func IPv4ToInt(ip net.IP) (uint32, error) {
	ip4 := ip.To4()
	if ip4 == nil {
		return 0, fmt.Errorf("not an ipv4 address")
	}
	return binary.BigEndian.Uint32(ip4), nil
}

// GetExternalIPInt queries external IP and returns it as uint32
func GetExternalIPInt() (uint32, error) {
	ip, err := GetExternalIP()
	if err != nil {
		return 0, err
	}
	return IPv4ToInt(ip)
}
