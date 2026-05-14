import json

# The key finding: CMP-23, 25, 26 completed scrape successfully but NEVER reached AI_EXT.
# CMP-24 DID reach AI_EXT (multiple SUCCESS entries). 
# CMP-24 is the one that succeeded.
# So something crashed between scrape and ai_extract for 23, 25, 26.

# Let's check: what was the exact sequence of events? 
# CMP-23 last scrape success at 17:00:17, then CMP-24 starts search at 17:00:24.
# This means CMP-23 crashed AFTER scrape but BEFORE AI_EXT was logged.

# Now let's check the May 8 logs to see if there were retry attempts
print("="*80)
print("FILE: pipeline_2026-05-08.jsonl")
print("="*80)
try:
    with open('output/logs/pipeline_2026-05-08.jsonl', 'r') as f:
        content = f.read().strip()
        if not content:
            print("(Empty file)")
        else:
            for line in content.split('\n'):
                try:
                    data = json.loads(line)
                    cid = data.get('company_id')
                    if cid in (23, 24, 25, 26):
                        ts = data.get('timestamp', '')
                        evt = data.get('event_type', '')
                        step = data.get('step', '')
                        status = data.get('status', '')
                        error = data.get('error_message', '')
                        print(f"[{ts}] CMP-{cid:04d} | {evt:20s} | {step:10s} | {status:10s} | {error[:100] if error else ''}")
                except:
                    pass
except FileNotFoundError:
    print("File not found")

# Now let's check git log to see when _extract_batch was introduced
# and what the code looked like on May 7
print()
print("="*80)
print("Checking git log for ai_extractor.py changes")
print("="*80)

