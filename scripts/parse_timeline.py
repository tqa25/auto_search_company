import json

# DETAILED timeline analysis for May 7
# Question: CMP-23 scrape completed at 17:00:17. CMP-24 started at 17:00:24.
# That means CMP-23's AI extract should have started between 17:00:17 and 17:00:24.
# But there's NO AI_EXT log for CMP-23. This means it crashed silently.

# Similarly for CMP-25: last scrape at 17:10:54, then CMP-26 starts at 17:11:02
# And CMP-26: last scrape at 17:12:55, then... nothing more.

# Let me check what the pipeline.py exception handling does when it catches an unknown error.
# From the code: except Exception as e: -> marks as 'failed' and breaks

# So the question is: what Exception was thrown?
# It's NOT logged in the JSONL because the crash happens in pipeline.py (the orchestrator),
# not inside ai_extractor.py. pipeline.py just prints to stdout.

# Let me check if there's stdout/stderr captured somewhere, or check the test_3step output
# from today which DID have stdout captured.

# CONCLUSION from today's run (output captured in command status):
# "[...] -> AI Extracting...
#  -> FAILED (unknown error): name 'company_name' is not defined"
# This was for ALL 3 companies (27, 28, 29).

# Now let me verify: Was this same bug present on May 7?
# Check the version of ai_extractor.py that was running on May 7.
# The _extract_batch function references company_name on line 567 (now 570).
# extract_for_company didn't define company_name before we fixed it.

# Let's look at what CMP-24 did differently - why did IT succeed?
print("="*80)
print("DETAILED: CMP-24 AI_EXT events on May 7")
print("="*80)

with open('output/logs/pipeline_2026-05-07.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get('company_id') == 24 and 'ai' in data.get('step', '').lower():
                ts = data.get('timestamp', '')
                evt = data.get('event_type', '')
                step = data.get('step', '')
                status = data.get('status', '')
                meta = data.get('metadata', {})
                print(f"[{ts}] {evt:15s} | {step:10s} | {status:10s} | meta={meta}")
        except:
            pass

# Now: CMP-24 had 8 AI_EXT SUCCESS entries + 1 SKIPPED + contact discovery scrapes.
# This means CMP-24's pages were all processed INDIVIDUALLY (not batched).
# The batch path (which triggers the bug) was NOT hit for CMP-24.

# Let's verify: how many scraped pages each company had, and their sizes
print()
print("="*80)
print("Scraped pages per company (count + content_length)")
print("="*80)

import sqlite3
conn = sqlite3.connect('data/company_data.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

for cid in [23, 24, 25, 26]:
    cursor.execute(
        "SELECT id, content_length, source_type FROM scraped_pages WHERE company_id = ? AND scrape_status = 'success' ORDER BY content_length",
        (cid,)
    )
    rows = cursor.fetchall()
    print(f"\nCMP-{cid:04d}: {len(rows)} scraped pages")
    for r in rows:
        print(f"  page_id={r['id']:4d} | len={r['content_length']:8d} | {r['source_type']}")

conn.close()

