"""
Health Monitor — System health monitoring and dashboard for the pipeline.

Provides real-time status tracking, credit usage estimation, completion time
prediction, and a formatted console dashboard for operators.
"""

import os
import datetime
from colorama import init, Fore, Back, Style
from src.database import DatabaseManager
from src.logger import PipelineLogger

init(autoreset=True)


class HealthMonitor:
    """Monitor pipeline health, track progress, estimate costs and completion time."""

    # Average credits per company (based on typical usage pattern)
    # Search: ~4-6 credits (2-3 search queries × 2 credits each)
    # Scrape: ~3-5 credits (3-5 pages × 1 credit each)
    # Total: ~7-11 credits per company, we use 5 as conservative estimate
    AVG_CREDITS_PER_COMPANY = 5.0

    # Firecrawl plan definitions
    FIRECRAWL_PLANS = {
        "free": {"name": "Free", "credits": 500, "cost": "$0"},
        "hobby": {"name": "Hobby ($19/mo)", "credits": 3000, "cost": "$19/mo"},
        "standard": {"name": "Standard ($99/mo)", "credits": 100000, "cost": "$99/mo"},
        "growth": {"name": "Growth ($399/mo)", "credits": 1000000, "cost": "$399/mo"},
    }

    def __init__(self, db: DatabaseManager, logger: PipelineLogger):
        self.db = db
        self.logger = logger

    # ------------------------------------------------------------------
    # Credit tracking
    # ------------------------------------------------------------------

    def check_credits_remaining(self, firecrawl_api_key: str = None) -> dict:
        """Calculate total credits used from DB and estimate remaining.
        
        Args:
            firecrawl_api_key: Not used for calculation (credits are tracked in DB),
                               but kept for interface consistency.
        
        Returns:
            Dict with credits_used, estimated plan, and warnings.
        """
        # Credits from search_results
        search_credits_row = self.db.fetch_one(
            "SELECT COALESCE(SUM(credits_used), 0) as total FROM search_results"
        )
        search_credits = float(search_credits_row['total']) if search_credits_row else 0.0

        # Credits from scraped_pages
        scrape_credits_row = self.db.fetch_one(
            "SELECT COALESCE(SUM(credits_used), 0) as total FROM scraped_pages"
        )
        scrape_credits = float(scrape_credits_row['total']) if scrape_credits_row else 0.0

        total_credits_used = search_credits + scrape_credits

        # Determine likely plan based on usage
        current_plan = "free"
        for plan_key in ["free", "hobby", "standard", "growth"]:
            plan = self.FIRECRAWL_PLANS[plan_key]
            if total_credits_used <= plan["credits"]:
                current_plan = plan_key
                break
        else:
            current_plan = "growth"

        plan_info = self.FIRECRAWL_PLANS[current_plan]
        credits_remaining = max(0, plan_info["credits"] - total_credits_used)

        # Warnings
        warnings = []
        usage_percent = (total_credits_used / plan_info["credits"] * 100) if plan_info["credits"] > 0 else 100
        if usage_percent >= 90:
            warnings.append(f"⚠️  CRITICAL: {usage_percent:.1f}% credits used! Consider upgrading plan.")
        elif usage_percent >= 75:
            warnings.append(f"⚠️  Warning: {usage_percent:.1f}% credits used.")

        return {
            "search_credits_used": search_credits,
            "scrape_credits_used": scrape_credits,
            "total_credits_used": total_credits_used,
            "estimated_plan": plan_info["name"],
            "plan_credits_total": plan_info["credits"],
            "credits_remaining": credits_remaining,
            "usage_percent": usage_percent,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Completion time estimation
    # ------------------------------------------------------------------

    def estimate_completion_time(self, remaining_companies: int) -> dict:
        """Estimate time and credits needed to complete remaining companies.
        
        Args:
            remaining_companies: Number of companies left to process.
        
        Returns:
            Dict with estimated hours, completion datetime, and credit needs.
        """
        # Calculate average time per company from pipeline_logs
        avg_row = self.db.fetch_one("""
            SELECT 
                COUNT(DISTINCT company_id) as completed_companies,
                SUM(duration_seconds) as total_duration
            FROM pipeline_logs 
            WHERE status = 'success'
        """)

        completed = avg_row['completed_companies'] if avg_row and avg_row['completed_companies'] else 0
        total_duration = float(avg_row['total_duration']) if avg_row and avg_row['total_duration'] else 0.0

        if completed > 0:
            avg_seconds_per_company = total_duration / completed
        else:
            # Default estimate: ~30 seconds per company (search + filter + scrape + AI)
            avg_seconds_per_company = 30.0

        estimated_seconds = remaining_companies * avg_seconds_per_company
        estimated_hours = estimated_seconds / 3600
        estimated_completion = datetime.datetime.now() + datetime.timedelta(seconds=estimated_seconds)

        # Credit estimation
        credits_row = self.db.fetch_one("""
            SELECT 
                COALESCE(SUM(credits_used), 0) as total_credits,
                COUNT(DISTINCT company_id) as companies
            FROM pipeline_logs 
            WHERE status = 'success'
        """)
        total_credits = float(credits_row['total_credits']) if credits_row and credits_row['total_credits'] else 0.0
        credit_companies = credits_row['companies'] if credits_row and credits_row['companies'] else 0

        if credit_companies > 0:
            avg_credits_per_company = total_credits / credit_companies
        else:
            avg_credits_per_company = self.AVG_CREDITS_PER_COMPANY

        estimated_credits = remaining_companies * avg_credits_per_company

        return {
            "remaining_companies": remaining_companies,
            "avg_seconds_per_company": round(avg_seconds_per_company, 1),
            "estimated_hours": round(estimated_hours, 1),
            "estimated_completion": estimated_completion.strftime("%Y-%m-%d %H:%M"),
            "estimated_credits_needed": round(estimated_credits),
            "avg_credits_per_company": round(avg_credits_per_company, 1),
        }

    # ------------------------------------------------------------------
    # System status
    # ------------------------------------------------------------------

    def get_system_status(self) -> dict:
        """Get comprehensive system status.
        
        Returns:
            Dict with total companies, completion stats, progress, estimates.
        """
        # Company status counts
        total_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")
        total_companies = total_row['cnt'] if total_row else 0

        done_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status = 'done'")
        completed = done_row['cnt'] if done_row else 0

        failed_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status = 'failed'")
        failed = failed_row['cnt'] if failed_row else 0

        perm_failed_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status = 'permanently_failed'")
        perm_failed = perm_failed_row['cnt'] if perm_failed_row else 0

        in_progress_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM companies WHERE status IN ('searching', 'scraping', 'extracting')"
        )
        in_progress = in_progress_row['cnt'] if in_progress_row else 0

        pending = total_companies - completed - failed - perm_failed - in_progress

        progress_percent = (completed / total_companies * 100) if total_companies > 0 else 0.0

        # Estimates
        remaining = total_companies - completed - perm_failed
        estimates = self.estimate_completion_time(remaining)
        credits_info = self.check_credits_remaining()

        return {
            "total_companies": total_companies,
            "completed": completed,
            "failed": failed,
            "permanently_failed": perm_failed,
            "in_progress": in_progress,
            "pending": pending,
            "progress_percent": round(progress_percent, 2),
            "estimated_hours_remaining": estimates["estimated_hours"],
            "estimated_completion": estimates["estimated_completion"],
            "estimated_credits_needed": estimates["estimated_credits_needed"],
            "current_plan": credits_info["estimated_plan"],
            "total_credits_used": credits_info["total_credits_used"],
            "credits_remaining": credits_info["credits_remaining"],
            "credit_sufficient": credits_info["credits_remaining"] >= estimates["estimated_credits_needed"],
        }

    # ------------------------------------------------------------------
    # Console dashboard
    # ------------------------------------------------------------------

    def print_dashboard(self):
        """Print a formatted, colorful system status dashboard to console."""
        status = self.get_system_status()
        credits_info = self.check_credits_remaining()

        width = 60

        print()
        print(Fore.CYAN + "=" * width)
        print(Fore.CYAN + Style.BRIGHT + "  📊 PIPELINE HEALTH DASHBOARD")
        print(Fore.CYAN + "=" * width)
        print()

        # Progress section
        print(Fore.WHITE + Style.BRIGHT + "  📈 TIẾN ĐỘ")
        print(Fore.WHITE + "  " + "-" * (width - 4))

        # Progress bar
        bar_width = 30
        filled = int(bar_width * status["progress_percent"] / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = status["progress_percent"]
        pct_color = Fore.GREEN if pct >= 75 else (Fore.YELLOW if pct >= 25 else Fore.RED)
        print(f"  Progress: [{pct_color}{bar}{Fore.WHITE}] {pct_color}{pct:.1f}%{Style.RESET_ALL}")
        print()

        print(f"  {'Tổng công ty:':<25} {status['total_companies']:>8}")
        print(f"  {Fore.GREEN}{'✅ Hoàn thành:':<25} {status['completed']:>8}{Style.RESET_ALL}")
        print(f"  {Fore.RED}{'❌ Thất bại:':<25} {status['failed']:>8}{Style.RESET_ALL}")
        if status['permanently_failed'] > 0:
            print(f"  {Fore.RED}{'💀 Thất bại vĩnh viễn:':<25} {status['permanently_failed']:>8}{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}{'⏳ Đang xử lý:':<25} {status['in_progress']:>8}{Style.RESET_ALL}")
        print(f"  {'🔲 Chờ xử lý:':<25} {status['pending']:>8}")
        print()

        # Credits section
        print(Fore.WHITE + Style.BRIGHT + "  💰 TÍN DỤNG (FIRECRAWL)")
        print(Fore.WHITE + "  " + "-" * (width - 4))
        print(f"  {'Gói hiện tại:':<25} {credits_info['estimated_plan']}")
        print(f"  {'Đã sử dụng:':<25} {credits_info['total_credits_used']:>8.0f} credits")
        print(f"    {'- Search:':<23} {credits_info['search_credits_used']:>8.0f}")
        print(f"    {'- Scrape:':<23} {credits_info['scrape_credits_used']:>8.0f}")
        
        remaining_color = Fore.GREEN if credits_info['usage_percent'] < 75 else (
            Fore.YELLOW if credits_info['usage_percent'] < 90 else Fore.RED
        )
        print(f"  {remaining_color}{'Còn lại:':<25} {credits_info['credits_remaining']:>8.0f} credits ({credits_info['usage_percent']:.1f}% used){Style.RESET_ALL}")
        print()

        # Estimation section
        print(Fore.WHITE + Style.BRIGHT + "  ⏱️  ƯỚC TÍNH")
        print(Fore.WHITE + "  " + "-" * (width - 4))
        print(f"  {'Thời gian còn lại:':<25} ~{status['estimated_hours_remaining']:.1f} giờ")
        print(f"  {'Dự kiến hoàn thành:':<25} {status['estimated_completion']}")
        print(f"  {'Credits cần thêm:':<25} ~{status['estimated_credits_needed']} credits")
        
        sufficient_color = Fore.GREEN if status['credit_sufficient'] else Fore.RED
        sufficient_text = "✅ Đủ" if status['credit_sufficient'] else "❌ Không đủ — cần nâng gói!"
        print(f"  {sufficient_color}{'Credits đủ?':<25} {sufficient_text}{Style.RESET_ALL}")
        print()

        # Warnings
        if credits_info['warnings']:
            print(Fore.RED + Style.BRIGHT + "  ⚠️  CẢNH BÁO")
            print(Fore.RED + "  " + "-" * (width - 4))
            for warning in credits_info['warnings']:
                print(f"  {Fore.RED}{warning}{Style.RESET_ALL}")
            print()

        print(Fore.CYAN + "=" * width)
        print()
