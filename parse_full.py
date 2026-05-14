import json

# Check the May 7 log for the ORIGINAL test (companies 23-26)
print("="*80)
print("FILE: pipeline_2026-05-07.jsonl (Lần chạy tuần trước)")
print("="*80)

with open('output/logs/pipeline_2026-05-07.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            cid = data.get('company_id')
            if cid in (23, 24, 25, 26):
                evt = data.get('event_type')
                step = data.get('step', '')
                status = data.get('status', '')
                error = data.get('error_message', '')
                ts = data.get('timestamp', '')
                if evt == 'step_end':
                    print(f"[{ts}] CMP-{cid:04d} | {step:10s} | {status:10s} | {error[:120] if error else ''}")
        except:
            pass

