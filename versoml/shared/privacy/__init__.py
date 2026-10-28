"""PrivacyProxy: recunoscători RO, seif de pseudonime, verificarea destinațiilor."""

from versoml.shared.privacy.proxy import PrivacyProxy, RawPIIError, assert_llm_safe, get_proxy, scan
from versoml.shared.privacy.recognizers import PII_TYPES, PUBLIC_ROLES, Finding, cnp_status, detect, is_card_number, mask
from versoml.shared.privacy.sinks import check_sink, explain_sink
from versoml.shared.privacy.text import fold, normalize_ro, strip_diacritics

__all__ = [
    "PII_TYPES",
    "PUBLIC_ROLES",
    "Finding",
    "PrivacyProxy",
    "RawPIIError",
    "assert_llm_safe",
    "check_sink",
    "cnp_status",
    "detect",
    "explain_sink",
    "fold",
    "get_proxy",
    "is_card_number",
    "mask",
    "normalize_ro",
    "scan",
    "strip_diacritics",
]
