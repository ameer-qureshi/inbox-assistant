"""Masks phone numbers and IBANs before any text is sent to the AI (bonus).

The AI provider is a third party: it does not need these values to classify
an email or draft a reply, so we never send them.
"""

import re

# IBAN: 2 letters, 2 digits, then 11-30 alphanumerics, optionally grouped by 4
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
# Phones: international (+33 6 12 34 56 78) or national (06 12 34 56 78, 06.12.34.56.78)
_PHONE = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{1,4}\)?[\s.-]?){2,5}\d{2,4}(?![\w])"
)


def _looks_like_phone(match: str) -> bool:
    digits = re.sub(r"\D", "", match)
    return 9 <= len(digits) <= 15


def mask_sensitive(text: str) -> str:
    text = _IBAN.sub("[IBAN]", text)
    return _PHONE.sub(lambda m: "[PHONE]" if _looks_like_phone(m.group()) else m.group(), text)
