import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from src.config import Config
from src.filter_module import LinkFilter

class TestLinkFilter(unittest.TestCase):
    def setUp(self):
        self.filter = LinkFilter(db=None, logger=None)



    def test_config_exposes_known_domains_from_pipeline_config(self):
        config = Config()
        self.assertIn("masothue.com", config.KNOWN_DOMAINS)

    def test_score_urls_batch_threads_tax_code_to_masothue_guard(self):
        results = self.filter.score_urls_batch(
            [{"url": "https://masothue.com/9999999999-wrong-company", "title": "Wrong"}],
            "Testing",
            tax_code="1234567890",
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["should_scrape"])

    def test_constructor_allows_missing_db_and_logger(self):
        link_filter = LinkFilter(db=None, logger=None)
        result = link_filter.classify_url("https://masothue.com/1234567890-test", "Testing", tax_code="1234567890")
        self.assertTrue(result["should_scrape"])

    def test_uses_known_domains_from_config(self):
        config = SimpleNamespace(
            BLACKLISTED_DOMAINS=[],
            SKIP_DOMAINS=[],
            KNOWN_DOMAINS={"custom-legal.vn": ("custom_legal", "legal")},
            DOMAIN_SCORES={"legal": 30, "unknown_web": 15, "official": 15},
            KEYWORD_SCORES={},
            TLD_SCORES={},
            SCRAPE_LINKEDIN_ENABLED=True,
            MIN_SCRAPE_SCORE=35,
            EARLY_STOP_SCORE=35,
        )
        link_filter = LinkFilter(db=None, logger=None, config=config)
        result = link_filter.classify_url("https://custom-legal.vn/company", "Testing")
        self.assertEqual(result["source_type"], "custom_legal")
        self.assertTrue(result["should_scrape"])

    def test_masothue_mst_exact_match_scrapes(self):
        result = self.filter.classify_url(
            "https://masothue.com/1234567890-test-company",
            "Testing",
            tax_code="1234567890",
        )
        self.assertEqual(result["source_type"], "masothue")
        self.assertTrue(result["should_scrape"])

    def test_masothue_mst_mismatch_does_not_scrape(self):
        result = self.filter.classify_url(
            "https://masothue.com/9999999999-test-company",
            "Testing",
            tax_code="1234567890",
        )
        self.assertEqual(result["source_type"], "masothue")
        self.assertFalse(result["should_scrape"])
        self.assertIn("masothue_tax_mismatch", result["reason"])

    def test_masothue_branch_suffix_is_not_allowed_as_match(self):
        result = self.filter.classify_url(
            "https://masothue.com/1234567890-001-test-branch",
            "Testing",
            tax_code="1234567890",
        )
        self.assertFalse(result["should_scrape"])
        self.assertIn("masothue_tax_mismatch", result["reason"])

    def test_classify_url_target_domain(self):
        # masothue.com is a legal domain
        result = self.filter.classify_url("https://masothue.com/1234", "Testing")
        self.assertEqual(result["source_type"], "masothue")
        self.assertTrue(result["should_scrape"])

    def test_classify_url_target_domain_subdomain(self):
        result = self.filter.classify_url("https://m.facebook.com/testing", "Testing")
        self.assertEqual(result["source_type"], "facebook")
        self.assertFalse(result["should_scrape"])

    def test_classify_url_skip_domain(self):
        result = self.filter.classify_url("https://www.youtube.com/watch?v=123", "Testing")
        self.assertEqual(result["source_type"], "other")
        self.assertFalse(result["should_scrape"])

    def test_classify_url_official_website(self):
        result = self.filter.classify_url("https://www.abcsoftware.com/about", "ABC Software")
        self.assertEqual(result["source_type"], "official_website")
        self.assertTrue(result["should_scrape"])

    def test_classify_url_edge_cases(self):
        # Should handle www correctly
        result = self.filter.classify_url("https://www.masothue.com/", "Testing")
        self.assertEqual(result["source_type"], "masothue")
        self.assertTrue(result["should_scrape"])

    def test_masothue_mismatch_does_not_poison_seen_domains_incremental(self):
        config = SimpleNamespace(
            BLACKLISTED_DOMAINS=[],
            SKIP_DOMAINS=[],
            KNOWN_DOMAINS={"masothue.com": ("masothue", "legal")},
            DOMAIN_SCORES={"legal": 30, "unknown_web": 15, "official": 15},
            KEYWORD_SCORES={},
            TLD_SCORES={},
            SCRAPE_LINKEDIN_ENABLED=True,
            MIN_SCRAPE_SCORE=35,
            EARLY_STOP_SCORE=30,
        )
        db = MagicMock()
        db.insert_filtered_link.side_effect = [1, 2]
        link_filter = LinkFilter(db=db, logger=None, config=config)
        seen_domains = set()

        first_results, first_good = link_filter.filter_urls_incremental(
            company_id=1,
            urls=[{"search_result_id": 1, "url": "https://masothue.com/9999999999-wrong", "title": "Wrong"}],
            seen_domains=seen_domains,
            company_name="Testing",
            tax_code="1234567890",
        )
        second_results, second_good = link_filter.filter_urls_incremental(
            company_id=1,
            urls=[{"search_result_id": 2, "url": "https://masothue.com/1234567890-right", "title": "Right"}],
            seen_domains=seen_domains,
            company_name="Testing",
            tax_code="1234567890",
        )

        self.assertEqual(first_good, 0)
        self.assertFalse(first_results[0]["should_scrape"])
        self.assertTrue(second_results[0]["should_scrape"])
        self.assertEqual(second_good, 1)
        self.assertIn("masothue.com", seen_domains)

if __name__ == '__main__':
    unittest.main()
