"""License services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)


def _refresh_legacy_globals() -> None:
    legacy.refresh_globals(globals(), exclude={"_refresh_legacy_globals"})


def api_payme_license_activate(payload: XFilesLicenseActivatePayload):
    _refresh_legacy_globals()
    return _xfiles_apply_invite_license(
        payload,
        action="activate",
        allowed_kinds={"activation"},
        success_message="Лицензия активирована",
    )

def api_payme_license_audit(limit: int = Query(default=50, ge=1, le=500)):
    _refresh_legacy_globals()
    return [XFilesLicenseAuditDTO(**item) for item in xfiles_read_license_audit_records(_xfiles_license_audit_path(), limit=limit)]

def api_payme_license_email_import():
    _refresh_legacy_globals()
    document, email_message_id = _xfiles_fetch_invite_license_from_email_sync()
    action = _xfiles_apply_invite_license(
        XFilesLicenseActivatePayload(invite_license=document),
        action="email_import",
        allowed_kinds={"activation", "renewal", "trial-extension", "upgrade", "addon", "update", "support"},
        success_message="Invite-license импортирован из email",
    )
    _save_app_settings({"license_email_last_import_at": _utc_now().isoformat()})

    receipt_sent = False
    if _get_app_settings().get("license_email_allow_activation_receipt"):
        try:
            receipt_sent = _xfiles_send_activation_receipt_email_sync(
                target_email=_xfiles_receipt_target_email(document)
            )
            _xfiles_append_license_audit(
                action="activation_receipt_email",
                ok=receipt_sent,
                document=document,
                status=action.status.model_dump(),
                error="" if receipt_sent else "activation receipt email skipped",
            )
        except Exception as exc:
            _xfiles_append_license_audit(
                action="activation_receipt_email",
                ok=False,
                document=document,
                status=action.status.model_dump(),
                error=str(exc),
            )
            logging.warning("x-files activation receipt email failed: %s", exc)

    return XFilesLicenseEmailImportDTO(
        ok=True,
        message=(
            "Invite-license импортирован из email"
            + ("; квитанция активации отправлена владельцу продукта" if receipt_sent else "")
        ),
        email_message_id=email_message_id,
        activation_receipt_sent=receipt_sent,
        status=action.status,
    )

def api_payme_license_menus():
    _refresh_legacy_globals()
    return XFilesLicenseMenusDTO(**_xfiles_menu_entitlements())

def api_payme_license_menus_check(payload: XFilesLicenseMenuCheckPayload):
    _refresh_legacy_globals()
    entitlements = _xfiles_menu_entitlements()
    allowed_set = set(entitlements.get("effective_allowed_menus") or [])
    requested = [str(item).strip() for item in payload.menus if str(item or "").strip()]
    if payload.menu and str(payload.menu).strip():
        requested.append(str(payload.menu).strip())
    if not requested:
        requested = [item["key"] for item in XFILES_MENU_CATALOG]
    return XFilesLicenseMenuCheckDTO(
        ok=bool(entitlements.get("ok")),
        status=str(entitlements.get("status") or "missing"),
        allowed={key: key in allowed_set for key in requested},
    )

def api_payme_license_renew(payload: XFilesLicenseActivatePayload):
    _refresh_legacy_globals()
    return _xfiles_apply_invite_license(
        payload,
        action="renew",
        allowed_kinds={"renewal", "trial-extension"},
        success_message="Лицензия продлена",
    )

def api_payme_license_status():
    _refresh_legacy_globals()
    return XFilesLicenseStatusDTO(**_xfiles_license_status_payload())

def api_payme_license_upgrade(payload: XFilesLicenseActivatePayload):
    _refresh_legacy_globals()
    return _xfiles_apply_invite_license(
        payload,
        action="upgrade",
        allowed_kinds={"upgrade", "addon"},
        success_message="Тариф обновлён без удаления данных",
    )

def api_payme_tariffs():
    _refresh_legacy_globals()
    status_payload = _xfiles_license_status_payload()
    source_usage = _xfiles_tariff_source_usage_payload(status_payload=status_payload)
    return {
        "plans": xfiles_tariff_catalog(),
        "current_plan": status_payload.get("plan"),
        "current_limits": status_payload.get("limits") if isinstance(status_payload.get("limits"), dict) else {},
        "current_features": status_payload.get("features") if isinstance(status_payload.get("features"), dict) else {},
        "source_limit": source_usage.get("limit"),
        "source_usage": source_usage,
        "limit_warnings": source_usage.get("messages") or [],
        "upgrade_hint": source_usage.get("upgrade_hint") or "",
    }

def api_payme_update_status():
    _refresh_legacy_globals()
    return _xfiles_update_status_payload()
