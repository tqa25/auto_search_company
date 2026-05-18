import json
import glob

log_files = glob.glob('output/logs/*.jsonl')

for log_file in log_files:
    print(f"Checking {log_file}...")
    with open(log_file, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get('status') == 'failed' and data.get('error_message'):
                    print(f"Company ID: {data.get('company_id')}, Step: {data.get('step')}, Error: {data.get('error_message')}")
            except Exception:
                pass
