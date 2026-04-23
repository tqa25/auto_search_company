import unittest
import urllib.parse
from src.filter_module import LinkFilter

class TestLinkFilter(unittest.TestCase):
    def setUp(self):
        # We don't need a real DB or logger just to test classify_url
        self.filter = LinkFilter(db=None, logger=None)

    def test_classify_url_target_domain(self):
        result = self.filter.classify_url("https://masothue.com/1234", "Testing")
        self.assertEqual(result["source_type"], "masothue")
        self.assertTrue(result["should_scrape"])

    def test_classify_url_target_domain_subdomain(self):
        result = self.filter.classify_url("https://m.facebook.com/testing", "Testing")
        self.assertEqual(result["source_type"], "facebook")
        self.assertTrue(result["should_scrape"])

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

if __name__ == '__main__':
    unittest.main()
