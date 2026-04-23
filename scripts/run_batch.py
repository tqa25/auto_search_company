#!/usr/bin/env python3
"""
run_batch.py — General-purpose batch runner for the company data pipeline.

Usage:
    python scripts/run_batch.py --limit 100 --offset 20 --delay 3.0
    python scripts/run_batch.py --resume --limit 100
    python scripts/run_batch.py --retry-failed
    python scripts/run_batch.py --dry-run --limit 100
"""

import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import Pipeline
from src.health_monitor import HealthMonitor
from src.database import DatabaseManager
from src.logger import PipelineLogger


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch runner for the company data extraction pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_batch.py --limit 100                   # Process 100 companies from the start
  python scripts/run_batch.py --limit 100 --offset 20       # Skip first 20, process next 100
  python scripts/run_batch.py --resume --limit 100           # Resume from last checkpoint, up to 100
  python scripts/run_batch.py --retry-failed                 # Retry all failed companies
  python scripts/run_batch.py --dry-run --limit 100          # Print plan without executing
        """
    )

    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of companies to process (required unless --retry-failed)"
    )
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Number of companies to skip from the beginning (default: 0)"
    )
    parser.add_argument(
        "--delay", type=float, default=3.0,
        help="Delay in seconds between API requests (default: 3.0)"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from the last checkpoint (ignores --offset)"
    )
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Retry all companies with status='failed'"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print execution plan without actually running"
    )

    args = parser.parse_args()

    # Validate: need --limit unless --retry-failed
    if not args.retry_failed and args.limit is None:
        parser.error("--limit is required unless --retry-failed is specified")

    return args


def main():
    # 1. Load .env
    load_dotenv()
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not firecrawl_key:
        print("❌ Error: FIRECRAWL_API_KEY not found in .env")
        sys.exit(1)

    args = parse_args()

    # 2. Initialize Pipeline + HealthMonitor
    config = {
        "firecrawl_api_key": firecrawl_key,
        "gemini_api_key": gemini_key,
        "delay_seconds": args.delay,
        "output_dir": "output",
    }

    pipeline = Pipeline(config)
    health = HealthMonitor(pipeline.db, pipeline.logger)

    # 3. Print dashboard
    health.print_dashboard()

    # 4. Handle --retry-failed
    if args.retry_failed:
        if args.dry_run:
            failed = pipeline.db.fetch_all("SELECT * FROM companies WHERE status = 'failed'")
            print(f"📋 DRY RUN: Would retry {len(failed)} failed companies:")
            for c in failed[:10]:
                print(f"  - ID {c['id']}: {c['original_name']}")
            if len(failed) > 10:
                print(f"  ... and {len(failed) - 10} more")
            return

        pipeline.retry_failed()
        _print_final_summary(pipeline, health, args)
        return

    # 5. Handle --resume
    if args.resume:
        resumable = pipeline.get_resumable_companies()
        if not resumable:
            print("✅ No companies to resume. All done!")
            return

        # Apply limit
        if args.limit and len(resumable) > args.limit:
            resumable = resumable[:args.limit]

        if args.dry_run:
            print(f"📋 DRY RUN: Would resume {len(resumable)} companies:")
            for item in resumable[:10]:
                print(f"  - ID {item['company_id']}: status={item['status']}, next_step={item['next_step']}")
            if len(resumable) > 10:
                print(f"  ... and {len(resumable) - 10} more")
            
            estimates = health.estimate_completion_time(len(resumable))
            print(f"\n⏱️  Estimated: ~{estimates['estimated_hours']:.1f} hours, ~{estimates['estimated_credits_needed']} credits")
            return

        # Confirm before running
        estimates = health.estimate_completion_time(len(resumable))
        _confirm_run(len(resumable), estimates)

        company_ids = [c["company_id"] for c in resumable]
        pipeline.run(company_ids=company_ids)
        _print_final_summary(pipeline, health, args)
        return

    # 6. Normal batch run
    all_companies = pipeline.db.get_all_companies()
    
    if args.offset > 0:
        all_companies = all_companies[args.offset:]
    if args.limit:
        all_companies = all_companies[:args.limit]

    company_ids = [c["id"] for c in all_companies]

    if not company_ids:
        print("❌ No companies to process with the given offset/limit.")
        return

    if args.dry_run:
        print(f"📋 DRY RUN: Would process {len(company_ids)} companies (offset={args.offset}, limit={args.limit}):")
        for c in all_companies[:10]:
            print(f"  - ID {c['id']}: {c['original_name']} (status: {c['status']})")
        if len(all_companies) > 10:
            print(f"  ... and {len(all_companies) - 10} more")

        estimates = health.estimate_completion_time(len(company_ids))
        print(f"\n⏱️  Estimated: ~{estimates['estimated_hours']:.1f} hours, ~{estimates['estimated_credits_needed']} credits")
        print(f"   Delay: {args.delay}s between requests")
        return

    # Confirm before running
    estimates = health.estimate_completion_time(len(company_ids))
    _confirm_run(len(company_ids), estimates)

    pipeline.run(company_ids=company_ids)
    _print_final_summary(pipeline, health, args)


def _confirm_run(num_companies: int, estimates: dict):
    """Ask user for confirmation before running the pipeline."""
    print(f"\n🔔 Sẽ xử lý {num_companies} công ty, ước tính ~{estimates['estimated_credits_needed']} credits.")
    print(f"   Thời gian ước tính: ~{estimates['estimated_hours']:.1f} giờ")
    user_input = input("   Tiếp tục? (y/n): ").strip().lower()
    if user_input != 'y':
        print("❌ Cancelled.")
        sys.exit(0)


def _print_final_summary(pipeline, health, args):
    """Print final summary after pipeline execution."""
    print("\n" + "=" * 60)
    print("  📊 KẾT QUẢ CHẠY BATCH")
    print("=" * 60)
    
    summary = pipeline.logger.get_daily_summary()
    print(f"  Total processed: {summary.get('total_processed_all', 0)}")
    print(f"  Success rate: {summary.get('success_rate', 0.0):.1f}%")
    print(f"  Total credits used: {summary.get('total_credits_used', 0.0):.0f}")
    print(f"  Avg time per company: {summary.get('avg_time_per_company', 0.0):.1f}s")

    # Generate reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join("output", f"batch_report_{timestamp}.xlsx")
    log_path = os.path.join("output", f"batch_log_{timestamp}.csv")

    pipeline.generate_report(report_path)
    pipeline.logger.export_log_to_csv(log_path)
    
    print(f"\n  📄 Report: {report_path}")
    print(f"  📄 Log: {log_path}")

    # Show updated dashboard
    print()
    health.print_dashboard()


if __name__ == "__main__":
    main()
