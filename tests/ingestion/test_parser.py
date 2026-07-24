import unittest
from unittest.mock import patch

from src.ingestion.parser import (
    GlobalRateLimiter,
    extract_sitemap_urls,
    is_full_catalog_source,
    parse_product_page,
    select_leaf_urls,
)


class ParserTests(unittest.TestCase):
    def test_global_rate_limiter_spaces_request_starts(self):
        limiter = GlobalRateLimiter(4)
        sleeps: list[float] = []
        with (
            patch("src.ingestion.parser.time.monotonic", side_effect=[10.0, 10.0]),
            patch("src.ingestion.parser.time.sleep", side_effect=sleeps.append),
        ):
            limiter.wait_for_turn()
            limiter.wait_for_turn()
        self.assertEqual(sleeps, [0.25])

    def test_extract_sitemap_urls_tolerates_malformed_tail(self):
        payload = b"<urlset><url><loc>https://remplanika.ru/catalog/a/</loc></url><broken>"
        self.assertEqual(extract_sitemap_urls(payload), ["https://remplanika.ru/catalog/a/"])


    def test_parse_realistic_remplanika_microdata(self):
        url = "https://remplanika.ru/catalog/tools/kisti/0112116_product/"
        page = """
        <html><body>
          <span class="vendorL">0112116</span>
          <meta itemprop="name" content="Кисть плоская &quot;Эксперт&quot;, 100 мм"/>
          <meta itemprop="category" content="РУЧНОЙ ИНСТРУМЕНТ/МАЛЯРНЫЙ ИНСТРУМЕНТ/КИСТИ"/>
          <meta itemprop="price" content="306"/>
          <meta itemprop="priceCurrency" content="RUB"/>
          <img src="/upload/product.jpg" itemprop="image"/>
        </body></html>
        """.encode("utf-8")
        product = parse_product_page(
            page,
            url,
            {"/catalog/tools/kisti/": {"category": "Инструменты", "subcategory": "Кисти"}},
        )
        self.assertIsNotNone(product)
        self.assertEqual(product["sku"], "0112116")
        self.assertEqual(product["price"], 306)
        self.assertEqual(product["subcategory"], "Кисти")
        self.assertEqual(product["image"], "https://remplanika.ru/upload/product.jpg")


    def test_category_page_is_not_a_product(self):
        self.assertIsNone(parse_product_page(b"<html><h1>Catalog</h1></html>", "https://remplanika.ru/catalog/", {}))

    def test_leaf_discovery_keeps_products_without_digits(self):
        urls = [
            "https://remplanika.ru/catalog/",
            "https://remplanika.ru/catalog/paint/",
            "https://remplanika.ru/catalog/paint/brand/",
            "https://remplanika.ru/catalog/paint/brand/product-without-digits/",
            "https://remplanika.ru/catalog/tools/brush-100/",
        ]
        self.assertEqual(
            select_leaf_urls(urls),
            [
                "https://remplanika.ru/catalog/paint/brand/product-without-digits/",
                "https://remplanika.ru/catalog/tools/brush-100/",
            ],
        )

    def test_full_catalog_scope_rejects_narrow_allowed_paths(self):
        self.assertTrue(
            is_full_catalog_source(
                {"catalog_scope": "full_catalog", "allowed_paths": ["/catalog/"]}
            )
        )
        self.assertFalse(
            is_full_catalog_source(
                {"catalog_scope": "full_catalog", "allowed_paths": ["/catalog/paint/"]}
            )
        )


if __name__ == "__main__":
    unittest.main()
