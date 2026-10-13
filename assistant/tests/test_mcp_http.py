"""Test serwera MCP przez HTTP (JSON-RPC), z prawdziwym uwierzytelnianiem tokenem."""

import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TransactionTestCase
from starlette.testclient import TestClient

from assistant.models import ApiToken
from assistant.tests.test_tools import make_company
from ksiegowosc.models import Contractor
from ksiegowosc.tests.test_settlements import make_invoice

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc(method, params=None, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


class McpHttpTests(TransactionTestCase):
    def setUp(self):
        from assistant import mcp_server

        self.user = User.objects.create_user("jan", password="x")
        make_company(self.user)
        contractor = Contractor.objects.create(
            user=self.user, name="Szpital", tax_id="1111111111"
        )
        make_invoice(self.user, contractor, "1/2026", date(2026, 1, 15), "10000")
        _, self.read_token = ApiToken.issue(self.user, "odczyt")
        self.app = mcp_server.build_app()

    def post(self, client, body, token):
        headers = dict(HEADERS)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return client.post("/mcp", content=json.dumps(body), headers=headers)

    def test_requires_token(self):
        with TestClient(self.app, base_url="http://127.0.0.1:8501") as client:
            r = self.post(client, rpc("tools/list"), None)
            self.assertEqual(r.status_code, 401)
            r = self.post(client, rpc("tools/list"), "fk_niepoprawny")
            self.assertEqual(r.status_code, 401)

    def test_list_and_call_tools(self):
        with TestClient(self.app, base_url="http://127.0.0.1:8501") as client:
            init = rpc(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            )
            r = self.post(client, init, self.read_token)
            self.assertEqual(r.status_code, 200, r.text)

            r = self.post(client, rpc("tools/list", id_=2), self.read_token)
            names = {t["name"] for t in r.json()["result"]["tools"]}
            self.assertIn("monthly_obligations", names)
            self.assertIn("save_monthly_settlement", names)

            call = rpc(
                "tools/call",
                {
                    "name": "monthly_obligations",
                    "arguments": {"year": 2026, "month": 1},
                },
                3,
            )
            result = self.post(client, call, self.read_token).json()["result"]
            self.assertFalse(result.get("isError"), result)
            self.assertEqual(
                result["structuredContent"]["ryczalt_za_miesiac"]["podatek"], "1368"
            )

            write = rpc(
                "tools/call",
                {
                    "name": "save_monthly_settlement",
                    "arguments": {"year": 2026, "month": 1},
                },
                4,
            )
            result = self.post(client, write, self.read_token).json()["result"]
            self.assertTrue(result["isError"])
            self.assertIn("tylko uprawnienie odczytu", result["content"][0]["text"])

    def test_wrong_host_is_rejected(self):
        with TestClient(self.app, base_url="http://zly-host.example") as client:
            r = self.post(client, rpc("tools/list"), self.read_token)
            self.assertIn(r.status_code, (401, 421))
