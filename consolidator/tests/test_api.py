"""Verifica la subida a la API con requests.post mockeado (no toca la red)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from consolidator.lib import api


class FakeResp:
    def __init__(self, status, text="OK"):
        self.status_code = status
        self.text = text


class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.f1 = d / "delta_parte_001.xlsx"
        self.f1.write_bytes(b"xlsx-1")
        self.f2 = d / "delta_parte_002.xlsx"
        self.f2.write_bytes(b"xlsx-2")

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch("consolidator.lib.api.requests.post")
    def test_uploads_each_part_and_respects_contract(self, post):
        post.return_value = FakeResp(200, "ok")
        res = api.upload_delta([self.f1, self.f2])
        self.assertEqual(len(res), 2)
        self.assertTrue(all(r["ok"] for r in res))
        self.assertEqual(post.call_count, 2)
        _, kwargs = post.call_args
        self.assertIn("X-API-Key", kwargs["headers"])
        self.assertIn("file", kwargs["files"])
        self.assertIn("id_usuario", kwargs["data"])

    @mock.patch("consolidator.lib.api.requests.post")
    def test_http_error_marks_not_ok(self, post):
        post.return_value = FakeResp(500, "boom")
        res = api.upload_delta([self.f1])
        self.assertFalse(res[0]["ok"])
        self.assertEqual(res[0]["status"], 500)

    @mock.patch("consolidator.lib.api.requests.post",
                side_effect=api.requests.exceptions.Timeout())
    def test_timeout_is_caught(self, post):
        res = api.upload_delta([self.f1])
        self.assertFalse(res[0]["ok"])
        self.assertIsNone(res[0]["status"])


if __name__ == "__main__":
    unittest.main()
