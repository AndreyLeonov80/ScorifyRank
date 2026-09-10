import unittest

from app.schemas import models
from app.schemas import analysis, channels, config, contacts, deals, license as license_schemas, monitoring
from app.schemas import routes
from app.schemas.compat_models import (
    AppSettingsDTO,
    RuntimeStatusDTO,
    TelegramDialogsPageDTO,
    XFilesDealDTO,
    XFilesLicenseStatusDTO,
)


class SchemaDomainFacadesTest(unittest.TestCase):
    def test_models_is_legacy_compatibility_re_export(self) -> None:
        self.assertIs(models.RuntimeStatusDTO, RuntimeStatusDTO)
        self.assertIs(models.TelegramDialogsPageDTO, TelegramDialogsPageDTO)
        self.assertIs(models.XFilesDealDTO, XFilesDealDTO)
        self.assertIn("XFilesDealDTO", models.__all__)

    def test_domain_facades_export_direct_domain_names(self) -> None:
        self.assertIs(config.AppSettingsDTO, AppSettingsDTO)
        self.assertIs(channels.TelegramDialogsPageDTO, TelegramDialogsPageDTO)
        self.assertIs(deals.XFilesDealDTO, XFilesDealDTO)
        self.assertIs(license_schemas.XFilesLicenseStatusDTO, XFilesLicenseStatusDTO)
        self.assertIn("ChatAnalysisPayload", analysis.__all__)
        self.assertIn("TelegramContactsPageDTO", contacts.__all__)
        self.assertIn("DuckDbStatusDTO", monitoring.__all__)
        self.assertIs(routes.RouteGeocodePayload, models.RouteGeocodePayload)


if __name__ == "__main__":
    unittest.main()
