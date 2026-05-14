# The batching logic: pages < 5000 chars are "short" and get grouped together.
# If there are >= 2 short pages in one batch, _extract_batch is called (requires company_name).
# If a "batch" has only 1 page, extract_from_page is called (has its own company_name lookup).

# CMP-24 pages: ALL are >= 5467 chars. No short pages!
# So CMP-24 NEVER enters the batching path → NEVER triggers the NameError.

# CMP-23 pages: 0, 2345, 3011 are all < 5000 chars. 3 short pages → BATCHED → NameError!
# CMP-25 pages: 116, 850, 970, 1184, 3446, 4843 are all < 5000 chars. 6 short pages → BATCHED → NameError!  
# CMP-26 pages: 724, 748, 784, 2956, 3975, 4248 are all < 5000 chars. 6 short pages → BATCHED → NameError!

THRESHOLD = 5000

companies_data = {
    23: [0, 2345, 3011, 6339, 10165, 14476, 17258, 29708, 88220],
    24: [5467, 8113, 10416, 15836, 16985, 17747, 17940, 22479, 23359, 24268, 26426],
    25: [116, 850, 970, 1184, 3446, 4843, 11072, 13438, 27694, 38613],
    26: [724, 748, 784, 2956, 3975, 4248, 7116, 26770, 28227, 44800],
}

print("="*80)
print(f"Batching threshold: pages < {THRESHOLD} chars are 'short' and get grouped")
print("="*80)

for cid, lengths in companies_data.items():
    short = [l for l in lengths if l < THRESHOLD]
    long = [l for l in lengths if l >= THRESHOLD]
    has_batch = len(short) >= 2  # 2+ short pages means _extract_batch will be called
    
    print(f"\nCMP-{cid:04d}:")
    print(f"  Total pages: {len(lengths)}")
    print(f"  Short pages (< {THRESHOLD}): {len(short)} → {short}")
    print(f"  Long pages (>= {THRESHOLD}): {len(long)}")
    print(f"  Will call _extract_batch? {'YES → NameError!' if has_batch else 'NO → extract_from_page (safe)'}")

print()
print("="*80)
print("KẾT LUẬN")
print("="*80)
print()
print("CMP-0024 (CÔNG TY TNHH AUDIENCE SERV):")
print("  → KHÔNG CÓ trang nào < 5000 chars")
print("  → Tất cả trang được xử lý riêng lẻ bằng extract_from_page()")
print("  → extract_from_page() có khai báo company_name riêng → KHÔNG BỊ LỖI")
print()
print("CMP-0023 (HYCO4 - JSC), CMP-0025 (CIRCO), CMP-0026 (SAIGON BOULEVARD):")
print("  → CÓ nhiều trang ngắn < 5000 chars")
print("  → Hệ thống gom cụm (batch) các trang ngắn và gọi _extract_batch()")
print("  → _extract_batch() cần biến company_name, nhưng extract_for_company() KHÔNG khai báo")
print("  → Crash: NameError: name 'company_name' is not defined")
print("  → Pipeline bắt exception → đánh dấu company status = 'failed'")

