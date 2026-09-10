import unittest

import back


class OcrSettingsTests(unittest.TestCase):
    def test_default_ocr_service_url_is_empty_for_client_delivery(self) -> None:
        settings = back._coerce_app_settings({})

        self.assertEqual(settings["ocr_service_url"], "")
        self.assertFalse(settings["ocr_images_enabled"])

    def test_ocr_service_url_is_normalized_for_settings(self) -> None:
        settings = back._coerce_app_settings({"ocr_service_url": "192.168.0.90/"})

        self.assertEqual(settings["ocr_service_url"], "http://192.168.0.90")

    def test_ocr_service_url_is_exposed_in_settings_dto(self) -> None:
        dto = back.AppSettingsDTO(**back._coerce_app_settings({"ocr_service_url": "http://192.168.0.90/"}))

        self.assertEqual(dto.ocr_service_url, "http://192.168.0.90")


if __name__ == "__main__":
    unittest.main()
