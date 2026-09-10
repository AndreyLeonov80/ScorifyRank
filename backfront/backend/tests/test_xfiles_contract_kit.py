import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import back


class XFilesContractKitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_deals = back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY)
        self._original_audit = back.telegram_sync.state.get(back.XFILES_DEAL_AUDIT_STATE_KEY)
        self._original_contracts = back.telegram_sync.state.get(back.XFILES_CONTRACTS_STATE_KEY)
        back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = {"items": []}
        back.telegram_sync.state[back.XFILES_CONTRACTS_STATE_KEY] = {"statuses": {}, "templates": []}
        back._xfiles_clear_deal_api_caches()

    def tearDown(self) -> None:
        if self._original_deals is None:
            back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = self._original_deals
        if self._original_audit is None:
            back.telegram_sync.state.pop(back.XFILES_DEAL_AUDIT_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = self._original_audit
        if self._original_contracts is None:
            back.telegram_sync.state.pop(back.XFILES_CONTRACTS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.XFILES_CONTRACTS_STATE_KEY] = self._original_contracts
        back._xfiles_clear_deal_api_caches()

    def _deal(self, stage: back.DealStage = "proposal") -> back.XFilesDealDTO:
        return back.XFilesDealDTO(
            id="deal-contract-1",
            title="Пилот X-Files для отдела продаж",
            stage=stage,
            score=80,
            expected_value=300000.0,
            probability=0.6,
            margin=0.5,
            expected_profit=90000.0,
            contact_key="contact:contract",
            contact_name="Анна Директор",
            company="ООО Ромашка ИНН 7701234567",
            source="contacts",
            source_chat="sales-chat",
            need="Нужно ускорить квалификацию лидов и подготовку КП.",
            product_match="X-Files revenue operating system",
            next_action="Отправить КП и согласовать договор",
            next_action_at="2026-05-07T12:00:00+00:00",
            notes="email anna@example.com, генеральный директор подписывает договор.",
            created_at="2026-05-06T08:00:00+00:00",
            updated_at="2026-05-06T09:00:00+00:00",
        )

    def test_contract_kit_generates_templates_proposal_checklist_and_status(self) -> None:
        fixed_now = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_list_jur_entities_rows", return_value=[]),
            patch.object(back, "_utc_now", return_value=fixed_now),
        ):
            deal = back._xfiles_upsert_deal(self._deal())
            templates_page = back.api_payme_deals_contract_templates()
            kit = back.api_payme_deal_contract_kit(deal.id)
            updated = back.api_payme_deal_contract_status(
                deal.id,
                back.XFilesDealContractStatusPayload(contract_status="sent"),
            )

        self.assertGreaterEqual(templates_page.total, 5)
        self.assertTrue(any(item.kind == "proposal" for item in templates_page.items))
        self.assertEqual(kit.contract_status, "proposal_ready")
        self.assertIn("КП для Анна Директор", kit.short_proposal)
        self.assertIn("X-Files revenue operating system", kit.proposal_document)
        self.assertFalse(kit.missing_fields)
        self.assertTrue(all(item.get("ok") for item in kit.checklist))
        self.assertEqual(updated.contract_status, "sent")

    def test_contract_metrics_count_statuses_missing_fields_and_closing_speed(self) -> None:
        fixed_now = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
        audit_rows = [
            back.XFilesDealAuditDTO(
                id="audit-qualified",
                ts="2026-05-06T08:00:00+00:00",
                action="stage",
                deal_id="deal-contract-1",
                deal_title="Пилот X-Files для отдела продаж",
                after_stage="qualified",
            ).model_dump(),
            back.XFilesDealAuditDTO(
                id="audit-proposal",
                ts="2026-05-06T11:00:00+00:00",
                action="stage",
                deal_id="deal-contract-1",
                deal_title="Пилот X-Files для отдела продаж",
                before_stage="qualified",
                after_stage="proposal",
            ).model_dump(),
            back.XFilesDealAuditDTO(
                id="audit-contract",
                ts="2026-05-06T16:00:00+00:00",
                action="stage",
                deal_id="deal-contract-1",
                deal_title="Пилот X-Files для отдела продаж",
                before_stage="proposal",
                after_stage="contract",
            ).model_dump(),
        ]
        with (
            patch.object(back, "duckdb", None),
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=False),
            patch.object(back.telegram_sync, "save_state", lambda: None),
            patch.object(back, "_list_jur_entities_rows", return_value=[]),
            patch.object(back, "_utc_now", return_value=fixed_now),
        ):
            back._xfiles_upsert_deal(self._deal("contract"))
            back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = {"items": audit_rows}
            back._xfiles_set_contract_status("deal-contract-1", "paid")
            metrics = back.api_payme_deals_contract_metrics()

        self.assertEqual(metrics.deals_total, 1)
        self.assertEqual(metrics.statuses.get("paid"), 1)
        self.assertEqual(metrics.signed_or_paid, 1)
        self.assertEqual(metrics.ready_to_send, 0)
        self.assertEqual(metrics.missing_fields_top, [])
        self.assertEqual(metrics.duration_metrics["qualified_to_proposal"]["hours"], 3.0)
        self.assertEqual(metrics.duration_metrics["proposal_to_contract"]["hours"], 5.0)
        self.assertIn("скорость", metrics.message.lower())


if __name__ == "__main__":
    unittest.main()
