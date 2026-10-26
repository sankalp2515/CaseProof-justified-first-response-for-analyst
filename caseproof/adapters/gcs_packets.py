"""Private create-only packet archive; packet JSON is not an evidence upload type."""

import re
from hashlib import sha256
from urllib.parse import quote

from caseproof.domain.contracts import canonical


def archive_packet(storage, packet):
    if packet.synthetic is not True or not re.fullmatch(
        r"SYNTH-PACKET-[a-f0-9]+", packet.packet_id
    ):
        raise ValueError("invalid synthetic packet")
    key = "packets/" + packet.packet_id + ".json"
    data = canonical(packet.model_dump(mode="json")).encode()
    response = storage.session.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{storage.bucket}/o",
        params={"uploadType": "media", "name": key, "ifGenerationMatch": 0},
        data=data,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code == 412:
        prior = storage.session.get(
            f"https://storage.googleapis.com/storage/v1/b/{storage.bucket}/o/{quote(key, safe='')}",
            params={"alt": "media"},
            timeout=30,
        )
        prior.raise_for_status()
        if sha256(prior.content).digest() != sha256(data).digest():
            raise ValueError("immutable_packet_archive_conflict")
    else:
        response.raise_for_status()
    return key
