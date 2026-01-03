#!/bin/bash
# Wait for all search results and aggregate them
echo "[Summarizer] Waiting for search results..."

# Wait for all JSON files
while [ ! -f /tmp/rein-results/google.json ] || [ ! -f /tmp/rein-results/bing.json ] || [ ! -f /tmp/rein-results/reddit.json ]; do
  echo "[Summarizer] Waiting for results from all sources..."
  sleep 1
done

echo "[Summarizer] All results received! Processing..."
sleep 2

# Aggregate results
cat > /tmp/rein-results/summary.json << 'JSON'
{
  "task": "alcohol distribution market research",
  "total_sources": 3,
  "total_results": 8,
  "sources": [
    {
      "name": "Google",
      "count": 3
    },
    {
      "name": "Bing", 
      "count": 2
    },
    {
      "name": "Reddit",
      "count": 3
    }
  ],
  "all_results": [
    "https://example.com/article1",
    "https://example.com/article2",
    "https://example.com/article3",
    "https://bing.example.com/page1",
    "https://bing.example.com/page2",
    "https://reddit.com/r/business/post1",
    "https://reddit.com/r/business/post2",
    "https://reddit.com/r/business/post3"
  ],
  "completed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

echo "[Summarizer] Summary created!"
echo "[Summarizer] Results: 8 sources from 3 websites"
echo "[Summarizer] File: /tmp/rein-results/summary.json"
