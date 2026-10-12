import logging
import re
from typing import Tuple, Optional
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TWOFACTOR_BASE_URL = "https://2factor.in/API/V1"


def clean_phone_number(mobile_number: str) -> str:
    """
    Standardize the phone number for 2Factor SMS gateway (India format with country code 91).
    E.g., '+91 98765 43210', '09876543210', or '9876543210' -> '919876543210'
    """
    digits = re.sub(r"\D", "", str(mobile_number or ""))
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if len(digits) == 10:
        return f"91{digits}"
    if len(digits) > 10 and digits.startswith("0"):
        digits = digits.lstrip("0")
        if len(digits) == 10:
            return f"91{digits}"
    return digits


def send_sms_otp_via_2factor(mobile_number: str, otp_code: str) -> Tuple[bool, str, Optional[str]]:
    """
    Sends the generated OTP code to the recipient mobile number via 2Factor API V1.

    Returns:
        (success: bool, message: str, session_id: Optional[str])

    Security & Safety:
    - Never logs the actual OTP code or API Key.
    - Handles timeouts and connection errors safely.
    - If TWOFACTOR_API_KEY is not configured or set to placeholder, falls back gracefully (with mock mode in DEBUG).
    """
    api_key = getattr(settings, "TWOFACTOR_API_KEY", "")
    template_name = getattr(settings, "TWOFACTOR_OTP_TEMPLATE_NAME", "")

    # Check if API key is present and configured
    if not api_key or api_key.strip() in ("", "your_actual_2factor_api_key", "YOUR_2FACTOR_API_KEY"):
        if getattr(settings, "DEBUG", False):
            logger.info("2Factor API key not configured. Running in local/mock development mode.")
            return True, "OTP simulated in development mode (API key not set).", None
        logger.error("2Factor API key is missing or not configured in production settings.")
        return False, "SMS gateway service is currently unavailable. Please contact support.", None

    formatted_phone = clean_phone_number(mobile_number)
    if len(formatted_phone) < 10:
        return False, "Invalid mobile number format.", None

    # Endpoint:
    # If template_name is provided: https://2factor.in/API/V1/{api_key}/SMS/{phone_number}/{otp_val}/{template_name}
    # Otherwise: https://2factor.in/API/V1/{api_key}/SMS/{phone_number}/{otp_val}
    if template_name and template_name.strip():
        url = f"{TWOFACTOR_BASE_URL}/{api_key.strip()}/SMS/{formatted_phone}/{otp_code}/{template_name.strip()}"
    else:
        url = f"{TWOFACTOR_BASE_URL}/{api_key.strip()}/SMS/{formatted_phone}/{otp_code}"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "DudhDairy-Backend/1.0"},
            timeout=8.0
        )
    except requests.exceptions.Timeout:
        logger.error("Timeout occurred while contacting 2Factor SMS gateway.")
        return False, "SMS gateway timed out. Please try again in a few moments.", None
    except requests.exceptions.RequestException as exc:
        logger.error("Connection error while contacting 2Factor SMS gateway: %s", type(exc).__name__)
        return False, "Unable to reach SMS gateway. Please try again later.", None

    try:
        data = response.json()
    except Exception:
        logger.error("2Factor returned non-JSON response with HTTP status %s", response.status_code)
        return False, "SMS gateway returned an unexpected response.", None

    status_str = str(data.get("Status", "")).strip().capitalize()
    details = data.get("Details", "")

    if response.status_code == 200 and status_str == "Success":
        # Details contains the 2Factor Session ID
        session_id = str(details) if details else None
        return True, "OTP sent successfully via SMS.", session_id
    else:
        # Failure from 2Factor
        # Do not expose internal gateway secrets, return safe message
        logger.warning(
            "2Factor rejected OTP request with Status='%s', Details='%s', HTTP=%s",
            status_str,
            details,
            response.status_code,
        )
        return False, f"SMS delivery failed: {details or 'Service rejected the request.'}", None
