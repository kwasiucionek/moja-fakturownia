# /home/fakturownia/app/ksef_utils/server.py

from typing import Any, Dict
from zeep import Client
from .utils import (
    get_challenge_timestamp,
    get_full_path,
    pretty_xml,
    read_file_bytes,
    sign_challange,
)

# === DODAJEMY IMPORTY KONFIGURACJI ===
from .config import TestConfig, ProdConfig


class KSEFService:
    """
    Main KSeF service class
    """

    def __init__(self, server_env_str: str):
        """
        Initializes KSEFService with a specific environment string.

        :param server_env_str: Either 'test' or 'prod'
        """
        # === WPROWADZAMY MODYFIKACJĘ ===
        # Na podstawie tekstu 'test' lub 'prod' tworzymy odpowiedni obiekt konfiguracyjny
        if server_env_str == "test":
            self.config = TestConfig()
        else:
            self.config = ProdConfig()
        # ===============================

        self.endpoints = self._get_endpoints()

    def _get_endpoints(self) -> Dict[str, str]:
        endpoints: Dict[str, str] = {}
        for endpoint in ["online", "batch", "common"]:
            wsdl_path = get_full_path(f"resources/KSeF-{endpoint}.yaml")
            client = Client(wsdl_path)
            service_url = f"{self.config.URL}/api/{endpoint}?wsdl"
            service = client.create_service(
                "{http://ksef.mf.gov.pl/schema/gtw/svc/online/types/2021/10/01/0001}onlineService",
                service_url,
            )
            endpoints[endpoint] = service
        return endpoints

    def auth_by_token(self, nip: str, token: str) -> "KSEFService":
        timestamp = get_challenge_timestamp(self.config.TIMEZONE)
        service = self.endpoints["online"]
        challange_resp = service.Challenge(
            ContextIdentifier={"type": "NIP", "identifier": nip},
            timestamp=timestamp,
        )
        challange = challange_resp.challenge
        signed_challange = sign_challange(challange, self.config.PUBLIC_KEY)
        session_resp = service.InitSessionToken(
            challenge=challange,
            challengeResponse={
                "challenge": challange,
                "challengeResponse": signed_challange,
            },
            identifier={"type": "NIP", "identifier": nip},
            token=token,
        )
        self.token = session_resp.sessionToken.token
        return self

    def send_invoice(self, invoice_path: str) -> Dict[str, Any]:
        invoice_bytes = read_file_bytes(invoice_path)
        service = self.endpoints["online"]
        resp = service.SendInvoice(
            invoiceHash={"hash": "hash", "alg": "alg", "encoding": "enc"},
            invoicePayload={"type": "xml", "payload": invoice_bytes},
        )
        return resp

    def get_session_status(self) -> Dict[str, Any]:
        service = self.endpoints["online"]
        resp = service.GetSessionStatus()
        return resp
