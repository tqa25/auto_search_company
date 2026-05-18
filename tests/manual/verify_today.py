import json

# Confirm today's run (CMP 27, 28, 29) also had the same error
print("="*80)
print("Xác nhận lỗi trong lần chạy hôm nay (CMP-27, 28, 29)")
print("="*80)

with open('output/logs/pipeline_2026-05-11.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            cid = data.get('company_id')
            if cid in (27, 28, 29):
                step = data.get('step', '')
                evt = data.get('event_type', '')
                if 'ai' in step.lower() or 'extract' in step.lower():
                    status = data.get('status', '')
                    error = data.get('error_message', '')
                    ts = data.get('timestamp', '')
                    print(f"[{ts}] CMP-{cid:04d} | {evt:15s} | {step:10s} | {status:10s} | {error[:100] if error else ''}")
        except:
            pass

# Also: the stdout from the run explicitly showed the error.
# Let me re-confirm there were no AI_EXT log entries for these companies either.
print()
print("Note: Console output from today's run showed:")
print('  -> AI Extracting...')
print('  -> FAILED (unknown error): name \'company_name\' is not defined')
print("  (for ALL 3 companies: 27, 28, 29)")

