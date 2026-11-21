"""Push rendered frames to a Tidbyt device or a Tronbyt server."""
import base64
import requests
from app import config


def push_image(image_bytes: bytes, installation_id: str = "monarch") -> dict:
    """Push a WebP image to the device.

    Tidbyt cloud answers with JSON; Tronbyt answers with plain text
    ("WebP received."), so a non-JSON body is a success, not an error.
    """
    payload = {
        "deviceID": config.TIDBYT_DEVICE_ID,
        "image": base64.b64encode(image_bytes).decode("utf-8"),
        "installationID": installation_id,
        "background": False,
    }
    resp = requests.post(
        f"{config.TIDBYT_API_BASE}/devices/{config.TIDBYT_DEVICE_ID}/push",
        json=payload,
        headers={"Authorization": f"Bearer {config.TIDBYT_API_KEY}"},
        timeout=30,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"status": resp.status_code, "body": resp.text.strip()[:200]}
