import unittest

from torznab import parse_torznab_results


class TorznabParserTests(unittest.TestCase):
    def test_reads_size_child_and_namespaced_attributes(self):
        xml = b"""<?xml version="1.0"?>
        <rss xmlns:torznab="http://torznab.com/schemas/2015/feed">
          <channel><item>
            <title>Big Buck Bunny</title>
            <link>https://example.invalid/download/1</link>
            <size>11499650543</size>
            <torznab:attr name="seeders" value="12" />
            <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:abc" />
          </item></channel>
        </rss>"""
        result = parse_torznab_results(xml)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["size"], "11499650543")
        self.assertEqual(result[0]["seeders"], "12")
        self.assertEqual(result[0]["url"], "magnet:?xt=urn:btih:abc")

    def test_supports_size_attribute_as_fallback(self):
        xml = b"""<rss xmlns:torznab="http://torznab.com/schemas/2015/feed">
        <channel><item><title>Fallback</title><link>https://example.invalid/a</link>
        <torznab:attr name="size" value="2048" />
        <torznab:attr name="seeders" value="2" />
        </item></channel></rss>"""
        result = parse_torznab_results(xml)

        self.assertEqual(result[0]["size"], "2048")

    def test_missing_size_stays_empty_and_invalid_links_are_skipped(self):
        xml = b"""<rss><channel>
        <item><title>No size</title><link>https://example.invalid/a</link></item>
        <item><title>Bad link</title><link>javascript:alert(1)</link></item>
        </channel></rss>"""
        result = parse_torznab_results(xml)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["size"], "")
        self.assertEqual(result[0]["url"], "https://example.invalid/a")

    def test_sorts_seeders_numerically_and_applies_limit(self):
        xml = b"""<rss xmlns:torznab="http://torznab.com/schemas/2015/feed">
        <channel>
          <item><title>Two</title><link>https://example.invalid/2</link>
            <torznab:attr name="seeders" value="2" /></item>
          <item><title>Ten</title><link>https://example.invalid/10</link>
            <torznab:attr name="seeders" value="10" /></item>
        </channel></rss>"""
        result = parse_torznab_results(xml, limit=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Ten")

    def test_raises_clear_error_for_torznab_error_response(self):
        xml = b"""<rss><channel><error code="201" description="Indexer unavailable" />
        </channel></rss>"""
        with self.assertRaisesRegex(RuntimeError, "Indexer unavailable"):
            parse_torznab_results(xml)


if __name__ == "__main__":
    unittest.main()
