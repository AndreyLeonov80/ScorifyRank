"""Shared local license helpers for X-Files client/root tooling."""

from .core import (
    LicenseError,
    append_migration_audit_record,
    apply_license,
    build_instance_hash,
    build_migration_audit_record,
    create_metadata_backup,
    license_status,
    load_license_state,
    load_signed_license,
    read_migration_audit_records,
    restore_metadata_backup,
    sign_payload,
    validate_schema_compatibility,
    verify_signed_document,
)

__all__ = [
    "LicenseError",
    "append_migration_audit_record",
    "apply_license",
    "build_instance_hash",
    "build_migration_audit_record",
    "create_metadata_backup",
    "license_status",
    "load_license_state",
    "load_signed_license",
    "read_migration_audit_records",
    "restore_metadata_backup",
    "sign_payload",
    "validate_schema_compatibility",
    "verify_signed_document",
]
