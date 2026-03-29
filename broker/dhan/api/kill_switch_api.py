import json

from broker.dhan.api.baseurl import get_url
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)

DHAN_BASE_URL = "https://api.dhan.co/v2"


def _get_headers(access_token: str, include_content_type: bool = False) -> dict:
    headers = {
        "Accept": "application/json",
        "access-token": access_token,
    }
    if include_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _raise_for_status(response) -> None:
    if response.status_code < 200 or response.status_code >= 300:
        raise Exception(
            f"Dhan API error: HTTP {response.status_code} - {response.text}"
        )


def get_kill_switch_status(access_token: str) -> str:
    """GET /v2/killswitch — returns 'ACTIVATED' or 'DEACTIVATED'."""
    client = get_httpx_client()
    url = get_url("/v2/killswitch")
    headers = _get_headers(access_token)

    response = client.get(url, headers=headers)
    _raise_for_status(response)

    data = json.loads(response.text)
    logger.info(f"Kill switch status response: {data}")

    kill_switch_status = data.get("killSwitchStatus", "DEACTIVATED")
    return "ACTIVATED" if kill_switch_status == "ACTIVATED" else "DEACTIVATED"


def activate_kill_switch(access_token: str) -> dict:
    """POST /v2/killswitch?killSwitchStatus=ACTIVATE — activates the kill switch."""
    client = get_httpx_client()
    url = get_url("/v2/killswitch") + "?killSwitchStatus=ACTIVATE"
    headers = _get_headers(access_token, include_content_type=True)

    response = client.post(url, headers=headers)
    _raise_for_status(response)

    data = json.loads(response.text)
    logger.info(f"Activate kill switch response: {data}")
    return data


def set_pnl_exit(access_token: str, profit_threshold: float, loss_threshold: float) -> dict:
    """POST /v2/pnlExit — registers P&L thresholds with the broker."""
    client = get_httpx_client()
    url = get_url("/v2/pnlExit")
    headers = _get_headers(access_token, include_content_type=True)

    payload = json.dumps({
        "profitThreshold": profit_threshold,
        "lossThreshold": loss_threshold,
    })

    response = client.post(url, headers=headers, content=payload)
    _raise_for_status(response)

    data = json.loads(response.text)
    logger.info(f"Set pnlExit response: {data}")
    return data
