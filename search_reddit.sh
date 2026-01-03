#!/bin/bash
# Simulate search on Reddit
echo "[Reddit Search] Starting search for 'alcohol distribution'..."
sleep 4
echo "[Reddit Search] Found discussion 1: https://reddit.com/r/business/post1"
sleep 1
echo "[Reddit Search] Found discussion 2: https://reddit.com/r/business/post2"
sleep 1
echo "[Reddit Search] Found discussion 3: https://reddit.com/r/business/post3"
sleep 1

# Save results
mkdir -p /tmp/rein-results
cat > /tmp/rein-results/reddit.json << 'JSON'
{
  "source": "Reddit",
  "results": [
    "https://reddit.com/r/business/post1",
    "https://reddit.com/r/business/post2",
    "https://reddit.com/r/business/post3"
  ],
  "count": 3
}
JSON

echo "[Reddit Search] Done. Saved to reddit.json"
