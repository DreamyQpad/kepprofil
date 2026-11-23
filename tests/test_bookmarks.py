"""A játékfüggő könyvjelzők tárolórétege."""
import unittest

import bookmarks


class AddRemoveTest(unittest.TestCase):
    def test_hozzaadas_jatekonkent_kulon(self):
        data = {}
        self.assertTrue(bookmarks.add(data, "Tarkov", "Wiki", "https://wiki.example/a"))
        self.assertTrue(bookmarks.add(data, "Más játék", "Útmutató", "https://guide.example"))
        self.assertEqual([item["title"] for item in bookmarks.items(data, "Tarkov")], ["Wiki"])
        self.assertEqual([item["title"] for item in bookmarks.items(data, "Más játék")], ["Útmutató"])
        self.assertEqual(bookmarks.items(data, bookmarks.GENERAL), [])

    def test_ugyanaz_az_url_nem_kerul_ketszer_be(self):
        data = {}
        bookmarks.add(data, "G", "Egy", "https://a.example")
        self.assertFalse(bookmarks.add(data, "G", "Más cím", "https://a.example"))
        self.assertEqual(len(bookmarks.items(data, "G")), 1)

    def test_csak_http_es_https_url(self):
        data = {}
        for url in ("javascript:alert(1)", "file:///C:/x", "data:text/html,x", "ftp://x", "", "nem url", None):
            self.assertFalse(bookmarks.add(data, "G", "x", url), url)
        self.assertEqual(bookmarks.items(data, "G"), [])

    def test_cim_vagasa_es_ures_cim_helyettesitese(self):
        data = {}
        bookmarks.add(data, "G", "x" * 100, "https://a.example")
        bookmarks.add(data, "G", "   ", "https://b.example/oldal")
        titles = [item["title"] for item in bookmarks.items(data, "G")]
        self.assertEqual(len(titles[0]), bookmarks.TITLE_MAX)
        self.assertEqual(titles[1], "b.example")

    def test_darabszam_hatar(self):
        data = {}
        for number in range(bookmarks.MAX_ITEMS):
            self.assertTrue(bookmarks.add(data, "G", f"c{number}", f"https://a.example/{number}"))
        self.assertFalse(bookmarks.add(data, "G", "tul sok", "https://a.example/tul"))
        self.assertEqual(len(bookmarks.items(data, "G")), bookmarks.MAX_ITEMS)

    def test_torles_index_szerint(self):
        data = {}
        for number in range(3):
            bookmarks.add(data, "G", f"c{number}", f"https://a.example/{number}")
        self.assertTrue(bookmarks.remove(data, "G", 1))
        self.assertEqual([item["title"] for item in bookmarks.items(data, "G")], ["c0", "c2"])

    def test_ervenytelen_torles_nem_dob(self):
        data = {}
        self.assertFalse(bookmarks.remove(data, "G", 0))
        bookmarks.add(data, "G", "c", "https://a.example")
        for index in (-1, 5, "x", None):
            self.assertFalse(bookmarks.remove(data, "G", index), index)
        self.assertEqual(len(bookmarks.items(data, "G")), 1)


class RobustnessTest(unittest.TestCase):
    def test_serult_adat_nem_dob_es_tiszta_listat_ad(self):
        for broken in ({"G": "nem lista"}, {"G": [1, "x", {"title": 3}, {"url": "https://ok.example"}]}, {"G": None}):
            result = bookmarks.items(broken, "G")
            self.assertIsInstance(result, list)
            self.assertTrue(all(isinstance(item["title"], str) and item["url"].startswith("http") for item in result))

    def test_items_masolatot_ad(self):
        data = {}
        bookmarks.add(data, "G", "c", "https://a.example")
        bookmarks.items(data, "G")[0]["title"] = "átírva"
        self.assertEqual(bookmarks.items(data, "G")[0]["title"], "c")

    def test_payload(self):
        data = {}
        bookmarks.add(data, "Tarkov", "Wiki", "https://wiki.example")
        self.assertEqual(bookmarks.payload(data, "Tarkov"),
                         {"game": "Tarkov", "items": [{"title": "Wiki", "url": "https://wiki.example"}]})
        self.assertEqual(bookmarks.payload(data, bookmarks.GENERAL)["items"], [])


if __name__ == "__main__":
    unittest.main()
