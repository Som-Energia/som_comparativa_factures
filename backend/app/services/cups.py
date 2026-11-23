"""Spanish CUPS structure and control letters (P.O. 10.8).

Reference: https://www.boe.es/diario_boe/txt.php?id=BOE-A-2009-19040
Validation does not establish that a supply point exists or belongs to a holder.
"""

import re


CONTROL_ALPHABET = "TRWAGMYFPDXBNJZSQVHLCKE"
CUPS_FORMAT = re.compile(r"ES[0-9]{16}[A-Z]{2}(?:[0-9][FPRCXYZ])?")


def normalize_cups(value: str) -> str:
    return re.sub(r"[\s-]+", "", value).upper()


def is_valid_cups(value: str) -> bool:
    if not isinstance(value, str):
        return False
    value = normalize_cups(value)
    if not CUPS_FORMAT.fullmatch(value):
        return False
    quotient, remainder = divmod(int(value[2:18]) % 529, 23)
    return value[18:20] == CONTROL_ALPHABET[quotient] + CONTROL_ALPHABET[remainder]
