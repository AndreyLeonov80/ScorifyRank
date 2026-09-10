import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContactQualificationUiContractTest(unittest.TestCase):
    def test_llm_timeout_keeps_popup_open_and_waiting(self) -> None:
        script = (ROOT / "js" / "script.api.js").read_text()
        react_contacts = (ROOT / "js" / "react.contacts.js").read_text()

        self.assertIn("isLongQualificationWait(error)", script)
        self.assertIn("Сервер отвечает слишком долго", script)
        self.assertIn("label: 'Ожидаем ответ ...'", script)
        self.assertIn("waiting: true", script)
        self.assertIn("this.waitForQualificationResult(contactKey, templateId);", script)
        self.assertIn("Сервер отвечает дольше обычного. Ожидаем ответ ...", script)
        self.assertIn("${progress.waiting ? 'Ожидаем ответ ...'", react_contacts)

        timeout_branch_start = script.index("if (this.isLongQualificationWait(e))")
        timeout_branch_end = script.index("this.qualificationError = humanizeApiError", timeout_branch_start)
        timeout_branch = script[timeout_branch_start:timeout_branch_end]

        self.assertIn("return;", timeout_branch)
        self.assertNotIn("this.closeQualificationDialog", timeout_branch)
        self.assertNotIn("this.stopQualificationProgress", timeout_branch)


if __name__ == "__main__":
    unittest.main()
