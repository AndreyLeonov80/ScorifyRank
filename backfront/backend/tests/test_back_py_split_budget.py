from pathlib import Path
import unittest


BACK_PY = Path(__file__).resolve().parents[1] / "back.py"


class BackPySplitBudgetTests(unittest.TestCase):
    def test_back_py_is_below_final_split_budget(self) -> None:
        size = BACK_PY.stat().st_size
        self.assertLessEqual(size, 250_000)

    def test_back_py_has_no_extracted_payme_route_decorators(self) -> None:
        source = BACK_PY.read_text(encoding="utf-8")
        forbidden_fragments = (
            '@app.get("/api/payme/deals',
            '@app.post("/api/payme/deals',
            '@app.get("/api/payme/images',
            '@app.get("/api/payme/search',
            '@app.get("/api/payme/contacts',
            '@app.get("/api/payme/crm',
            '@app.get("/api/payme/outreach',
        )
        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
