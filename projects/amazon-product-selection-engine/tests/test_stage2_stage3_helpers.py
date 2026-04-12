# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine")
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


common = load_module(
    "amazon_selection_common",
    PROJECT_ROOT / "scripts/amazon_selection_common.py",
)
stage2 = load_module(
    "extract_stage2_primary_keywords",
    PROJECT_ROOT / "scripts/extract_stage2_primary_keywords.py",
)
stage3_all = load_module(
    "run_stage3_all_alternate_keyword_collection",
    PROJECT_ROOT / "scripts/run_stage3_all_alternate_keyword_collection.py",
)
stage3_hybrid = load_module(
    "run_stage3_hybrid_keyword_collection",
    PROJECT_ROOT / "scripts/run_stage3_hybrid_keyword_collection.py",
)


class Stage2Stage3HelperTests(unittest.TestCase):
    def test_parse_human_count(self):
        self.assertEqual(common.parse_human_count("2K+"), 2000)
        self.assertEqual(common.parse_human_count("3.8K"), 3800)
        self.assertEqual(common.parse_human_count("1,697"), 1697)

    def test_extract_primary_keyword(self):
        keyword = common.extract_primary_keyword(
            "Garden Kneeler and Seat Heavy Duty, Wider and Thicker Kneeling Pad for Foldable Gardening Stool",
            brand="Poraise",
            subcategory="Gardening Workseats",
        )
        self.assertEqual(keyword, "garden kneeler and seat")

    def test_parse_launch_date(self):
        date_value, age_days = common.parse_launch_date("Launch Date:2021-08-16 (1,697days)")
        self.assertEqual(date_value, "2021-08-16")
        self.assertEqual(age_days, 1697)

    def test_parse_amazon_result_count(self):
        self.assertEqual(common.parse_amazon_result_count('1-48 of 416 results for "garden kneeler and seat"'), 416)

    def test_parse_card_metrics(self):
        card_text = """Garden Kneeler and Seat Heavy Duty
4.6 out of 5 stars
(64)
1K+ bought in past month
Variation Sold(30 days):1,000+
Launch Date:2025-12-22 (109days)
Rating:
4.6(64)
"""
        self.assertEqual(common.parse_card_review_count(card_text), 64)
        self.assertEqual(common.parse_card_sales_30d(card_text), 1000)
        self.assertEqual(common.parse_card_rating(card_text), 4.6)

    def test_build_alternate_keyword_entries_and_unique_queue(self):
        product_rows = [
            {
                "source_rank": 1,
                "asin": "B0TEST0001",
                "product_url": "https://www.amazon.com/dp/B0TEST0001",
                "product_title": "Garden Kneeler and Seat Heavy Duty",
                "brand": "BrandA",
                "category_path": "Patio, Lawn & Garden:Gardening & Lawn Care:Gardening Workseats",
                "subcategory": "Gardening Workseats",
                "seller_type": "FBA",
                "sales_30d": 1200,
                "ratings_count": 100,
                "primary_keyword": "garden kneeler and seat",
                "alternate_keywords": "garden kneeler and seat|gardening workseats",
            },
            {
                "source_rank": 2,
                "asin": "B0TEST0002",
                "product_url": "https://www.amazon.com/dp/B0TEST0002",
                "product_title": "Garden Hose Lightweight",
                "brand": "BrandB",
                "category_path": "Patio, Lawn & Garden:Gardening & Lawn Care:Watering Equipment:Garden Hoses",
                "subcategory": "Garden Hoses",
                "seller_type": "FBM",
                "sales_30d": 900,
                "ratings_count": 50,
                "primary_keyword": "garden hose non-expanding",
                "alternate_keywords": "garden hose non-expanding|garden hoses|garden kneeler and seat",
            },
        ]

        alternate_entries = stage2.build_alternate_keyword_entries(product_rows)
        unique_keywords = stage2.build_unique_alternate_keywords(alternate_entries)

        self.assertEqual(len(alternate_entries), 5)
        self.assertEqual(len(unique_keywords), 4)
        self.assertEqual(unique_keywords[0]["keyword"], "garden kneeler and seat")
        self.assertEqual(unique_keywords[0]["alternate_keyword_occurrence_count"], 2)
        self.assertEqual(unique_keywords[0]["alternate_keyword_source_asin_count"], 2)
        self.assertEqual(unique_keywords[1]["keyword"], "gardening workseats")

    def test_build_expanded_rows_maps_metrics_back_to_every_alternate_entry(self):
        alternate_entries = [
            {
                "alternate_keyword_entry_rank": 1,
                "source_rank": 1,
                "asin": "B0TEST0001",
                "product_url": "https://www.amazon.com/dp/B0TEST0001",
                "product_title": "Garden Kneeler and Seat Heavy Duty",
                "brand": "BrandA",
                "category_path": "category",
                "subcategory": "subcategory",
                "seller_type": "FBA",
                "sales_30d": 1200,
                "ratings_count": 100,
                "primary_keyword": "garden kneeler and seat",
                "alternate_keyword_position": 1,
                "alternate_keyword": "garden kneeler and seat",
            },
            {
                "alternate_keyword_entry_rank": 2,
                "source_rank": 2,
                "asin": "B0TEST0002",
                "product_url": "https://www.amazon.com/dp/B0TEST0002",
                "product_title": "Another Product",
                "brand": "BrandB",
                "category_path": "category",
                "subcategory": "subcategory",
                "seller_type": "FBM",
                "sales_30d": 900,
                "ratings_count": 50,
                "primary_keyword": "garden hose non-expanding",
                "alternate_keyword_position": 3,
                "alternate_keyword": "garden kneeler and seat",
            },
        ]
        metric_rows = [
            {
                "keyword_rank": 1,
                "keyword": "garden kneeler and seat",
                "result_count": 416,
                "first_page_product_link_total": 18,
                "review_avg": 320.4,
                "sales_30d_avg": 780.0,
                "representative_product_url": "https://www.amazon.com/dp/B0REP00001",
                "collection_status": "ok",
                "collection_error": "",
            }
        ]

        expanded_rows = stage3_all.build_expanded_rows(alternate_entries, metric_rows)
        self.assertEqual(len(expanded_rows), 2)
        self.assertEqual(expanded_rows[0]["keyword_rank"], 1)
        self.assertEqual(expanded_rows[1]["keyword_rank"], 1)
        self.assertEqual(expanded_rows[1]["result_count"], 416)
        self.assertEqual(expanded_rows[1]["representative_product_url"], "https://www.amazon.com/dp/B0REP00001")

    def test_hybrid_materialize_rows_preserves_keyword_queue_order(self):
        keyword_rows = [
            {"keyword": "kw-a"},
            {"keyword": "kw-b"},
            {"keyword": "kw-c"},
        ]
        metric_by_keyword = {
            "kw-c": {"keyword": "kw-c", "collection_status": "ok"},
            "kw-a": {"keyword": "kw-a", "collection_status": "ok"},
        }
        detail_by_keyword = {
            "kw-c": [{"keyword": "kw-c", "asin": "C1"}],
            "kw-a": [{"keyword": "kw-a", "asin": "A1"}, {"keyword": "kw-a", "asin": "A2"}],
        }
        metric_rows = stage3_hybrid.materialize_metric_rows(keyword_rows, metric_by_keyword)
        detail_rows = stage3_hybrid.materialize_detail_rows(keyword_rows, detail_by_keyword)
        self.assertEqual([row["keyword"] for row in metric_rows], ["kw-a", "kw-c"])
        self.assertEqual([row["asin"] for row in detail_rows], ["A1", "A2", "C1"])

    def test_hybrid_completed_statuses_include_empty(self):
        self.assertTrue(stage3_hybrid.is_completed_status("ok"))
        self.assertTrue(stage3_hybrid.is_completed_status("empty"))
        self.assertFalse(stage3_hybrid.is_completed_status("blocked"))


if __name__ == "__main__":
    unittest.main()
