import json

# Check: Did companies 23, 25, 26 ever reach AI_EXT step on May 7?
print("="*80)
print("Checking if CMP-23, 25, 26 ever reached AI_EXT step on May 7")
print("="*80)

ai_ext_seen = {23: False, 25: False, 26: False}

with open('output/logs/pipeline_2026-05-07.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            cid = data.get('company_id')
            if cid in (23, 25, 26):
                step = data.get('step', '')
                evt = data.get('event_type', '')
                if 'ai' in step.lower() or 'extract' in step.lower() or 'AI_EXT' in step:
                    ai_ext_seen[cid] = True
                    status = data.get('status', '')
                    error = data.get('error_message', '')
                    ts = data.get('timestamp', '')
                    print(f"[{ts}] CMP-{cid:04d} | {step:10s} | {evt:15s} | {status:10s} | {error[:100] if error else ''}")
        except:
            pass

print()
for cid, seen in ai_ext_seen.items():
    print(f"CMP-{cid:04d}: AI_EXT step reached = {seen}")

# Now check if there were any error events or company status changes logged
print()
print("="*80)
print("Checking all events for CMP-23 on May 7 (last few)")
print("="*80)
events_23 = []
with open('output/logs/pipeline_2026-05-07.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('company_id') == 23:
                events_23.append(data)
        except:
            pass

# Show last 5 events
for evt in events_23[-5:]:
    print(f"[{evt.get('timestamp')}] type={evt.get('event_type')} step={evt.get('step','')} status={evt.get('status','')} error={str(evt.get('error_message',''))[:120]}")

print()
print("="*80)
print("Checking all events for CMP-25 on May 7 (last few)")
print("="*80)
events_25 = []
with open('output/logs/pipeline_2026-05-07.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('company_id') == 25:
                events_25.append(data)
        except:
            pass
for evt in events_25[-5:]:
    print(f"[{evt.get('timestamp')}] type={evt.get('event_type')} step={evt.get('step','')} status={evt.get('status','')} error={str(evt.get('error_message',''))[:120]}")

print()
print("="*80)
print("Checking all events for CMP-26 on May 7 (last few)")
print("="*80)
events_26 = []
with open('output/logs/pipeline_2026-05-07.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('company_id') == 26:
                events_26.append(data)
        except:
            pass
for evt in events_26[-5:]:
    print(f"[{evt.get('timestamp')}] type={evt.get('event_type')} step={evt.get('step','')} status={evt.get('status','')} error={str(evt.get('error_message',''))[:120]}")

