"""QR generation placeholder."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class QRPayload:
    identifier: str
    link: Optional[str] = None


def generate_qr_payload(identifier: str, link: Optional[str] = None) -> QRPayload:
    return QRPayload(identifier=identifier, link=link)
