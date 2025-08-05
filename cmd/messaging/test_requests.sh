#!/bin/bash

# Test script for messaging server endpoints
# Make sure the server is running before executing this script

BASE_URL="http://localhost:8888"
MESSAGE="I solemnly swear that I am up to some good. Hotkey: 5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"
SIGNATURE="0x8ee4ce50165f23b739ec55c2beeafcd273685819c32470df26b0641d15593d3b08b8aef7c391f01e7c2e34c2ee12b80df0c4b615cc0d0966be0dc81192bbc286"
HOTKEY="5Eq1FDc9oz1tTm4MqGLdH4ajgz9eMgQ5To812axojN121DiQ"

# Function to make authenticated POST requests
make_request() {
    local endpoint="$1"
    local data="$2"
    curl -s -X POST "$BASE_URL/$endpoint" \
        -H "Content-Type: application/json" \
        -H "signature: $SIGNATURE" \
        -H "x-message: $MESSAGE" \
        -H "x-hotkey: $HOTKEY" \
        -d "$data" | jq .
}

# Function to make authenticated POST requests with compression
make_compressed_request() {
    local endpoint="$1"
    local data="$2"
    local original_size=$(echo -n "$data" | wc -c)
    
    # Create temporary file for compressed data
    local temp_file=$(mktemp)
    echo -n "$data" | zstd -c > "$temp_file"
    local compressed_size=$(wc -c < "$temp_file")
    
    echo "Original size: $original_size bytes, Compressed size: $compressed_size bytes ($(echo "scale=1; $compressed_size * 100 / $original_size" | bc)% of original)"
    
    curl -s -X POST "$BASE_URL/$endpoint" \
        -H "Content-Type: application/json" \
        -H "Content-Encoding: zstd" \
        -H "signature: $SIGNATURE" \
        -H "x-message: $MESSAGE" \
        -H "x-hotkey: $HOTKEY" \
        --data-binary "@$temp_file" | jq .
    
    rm "$temp_file"
}

echo "Testing messaging server endpoints..."
echo "====================================="

# Test health endpoint
echo
echo "1. Testing health endpoint:"
curl -s "$BASE_URL/health" | jq .

# Test PingRequest endpoint
echo
echo "2. Testing PingRequest endpoint:"
make_request "PingRequest" '{"message": "hello world"}'

# Test UserRequest endpoint (success)
echo
echo "3. Testing UserRequest endpoint (success):"
make_request "UserRequest" '{"name": "John Doe", "email": "john@example.com"}'

# Test UserRequest endpoint (error - empty name)
echo
echo "4. Testing UserRequest endpoint (error - empty name):"
make_request "UserRequest" '{"name": "", "email": "john@example.com"}'

# Test CalculateRequest endpoint (success)
echo
echo "5. Testing CalculateRequest endpoint (success):"
make_request "CalculateRequest" '{"a": 10, "b": 5}'

# Test CalculateRequest endpoint (error - division by zero)
echo
echo "6. Testing CalculateRequest endpoint (error - division by zero):"
make_request "CalculateRequest" '{"a": 10, "b": 0}'

# Test invalid JSON
echo
echo "7. Testing invalid JSON:"
make_request "PingRequest" 'invalid json'

# Test signature verification endpoint
echo
echo "8. Testing signature verification endpoint:"
make_request "substrate/sign-message/verify" "{\"message\": \"$MESSAGE\", \"signature\": \"$SIGNATURE\", \"signeeAddress\": \"$HOTKEY\"}"

# Test non-existent endpoint
echo
echo "9. Testing non-existent endpoint:"
make_request "NonExistentRequest" '{"test": "data"}'

echo
echo "====================================="
echo "ZSTD COMPRESSION TESTS"
echo "====================================="

# Create a large JSON payload for better compression demonstration
LARGE_PAYLOAD='{"message": "This is a test message with repetitive content to demonstrate compression effectiveness. This is a test message with repetitive content to demonstrate compression effectiveness. This is a test message with repetitive content to demonstrate compression effectiveness. This is a test message with repetitive content to demonstrate compression effectiveness. This is a test message with repetitive content to demonstrate compression effectiveness.", "data": ["item1", "item2", "item3", "item4", "item5", "item1", "item2", "item3", "item4", "item5", "item1", "item2", "item3", "item4", "item5", "item1", "item2", "item3", "item4", "item5"]}'

# Test PingRequest with compression
echo
echo "10. Testing PingRequest with ZSTD compression:"
make_compressed_request "PingRequest" "$LARGE_PAYLOAD"

# Test UserRequest with compression
echo
echo "11. Testing UserRequest with ZSTD compression:"
LARGE_USER_PAYLOAD='{"name": "John Doe with a very long name that includes repetitive information for compression testing purposes repetitive information for compression testing purposes repetitive information for compression testing purposes", "email": "john.doe.with.very.long.email.address.for.testing.compression@example.com"}'
make_compressed_request "UserRequest" "$LARGE_USER_PAYLOAD"

# Test CalculateRequest with compression
echo
echo "12. Testing CalculateRequest with ZSTD compression:"
make_compressed_request "CalculateRequest" '{"a": 12345, "b": 67890}'

# Test with JSON containing arrays and nested objects
echo
echo "13. Testing complex JSON with ZSTD compression:"
COMPLEX_PAYLOAD='{"users": [{"name": "User1", "data": "repetitive data repetitive data repetitive data"}, {"name": "User2", "data": "repetitive data repetitive data repetitive data"}, {"name": "User3", "data": "repetitive data repetitive data repetitive data"}], "metadata": {"version": "1.0", "description": "This is a complex payload with nested structures and repetitive content for compression testing"}}'
make_compressed_request "PingRequest" "$COMPLEX_PAYLOAD"

echo
echo "====================================="
echo "Test script completed!"