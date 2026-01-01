#!/bin/bash
# Simulate search on Bing
echo "[Bing Search] Starting search for 'alcohol distribution'..."
sleep 2
echo "[Bing Search] Found result 1: https://bing.example.com/page1"
sleep 2
echo "[Bing Search] Found result 2: https://bing.example.com/page2"
sleep 1

# Save results
mkdir -p /tmp/dog-results
cat > /tmp/dog-results/bing.json << 'JSON'
{
  "source": "Bing",
  "results": [
    "https://bing.example.com/page1",
    "https://bing.example.com/page2"
  ],
  "count": 2
}
JSON

echo "[Bing Search] Done. Saved to bing.json"
