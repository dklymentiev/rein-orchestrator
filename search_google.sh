#!/bin/bash
# Simulate search on Google
echo "[Google Search] Starting search for 'alcohol distribution'..."
sleep 3
echo "[Google Search] Found result 1: https://example.com/article1"
sleep 2
echo "[Google Search] Found result 2: https://example.com/article2"
sleep 2
echo "[Google Search] Found result 3: https://example.com/article3"

# Save results
mkdir -p /tmp/rein-results
cat > /tmp/rein-results/google.json << 'JSON'
{
  "source": "Google",
  "results": [
    "https://example.com/article1",
    "https://example.com/article2", 
    "https://example.com/article3"
  ],
  "count": 3
}
JSON

echo "[Google Search] Done. Saved to google.json"
