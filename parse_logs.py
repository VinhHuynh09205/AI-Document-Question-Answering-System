import re
import json

def parse_and_sort(log_file, pattern, key, limit=10):
    matches = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            if pattern in line:
                # Try to extract JSON-like structure or use regex for the key
                try:
                    # Generic regex to find "key": value or key=value
                    match = re.search(rf'"{key}"\s*:\s*([\d\.]+)|{key}=([\d\.]+)', line)
                    if match:
                        val = float(match.group(1) or match.group(2))
                        matches.append((val, line.strip()))
                except Exception:
                    continue
    
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:limit]

log_file = 'tmp/api_logs_24h.txt'
sections = [
    ("ingestion_file_processed", "ingestion_duration_ms"),
    ("document_ingestion_completed", "ingestion_total_time_ms"),
    ("embedding_batch_completed", "latency_ms"),
    ("[Retrieval]", "retrieval_ms")
]

for pattern, key in sections:
    print(f"\n--- Top 10: {pattern} by {key} ---")
    results = parse_and_sort(log_file, pattern, key)
    for val, line in results:
        print(f"[{val}] {line}")
