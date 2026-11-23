import pytest

from app.services.cups import is_valid_cups, normalize_cups
from app.services.invoice_extractor import extract_from_text


@pytest.mark.parametrize(("value", "valid"), [
    ("ES0987543210987654ZF", True),  # Published P.O. 10.8 examples.
    ("es 1234-123456789012-jy 1f", True),
    ("ES1234123456789012JY1P", True),
    ("ES9750210987654321CQ1C", True),
    ("ES0999110012345678EK1X", True),
    ("ES0987543210987654ZG", False),
    ("ES0987543210987655ZF", False),
    ("ES1234123456789012JY1T", False),
    ("ES1234123456789012JY1", False),
    ("ES1234123456789012JYFF", False),
    ("ES1234123456789012JY1F0", False),
    ("FR1234123456789012JY", False),
    ("ES１２３４１２３４５６７８９０１２JY", False),
    ("ES001234567890123456", False),  # IBAN-shaped fragment, not a CUPS.
    ("ES00 1234 5678 9012 3456 7890", False),
    (None, False),
    ("", False),
])
def test_cups_structure_and_control_letters(value, valid):
    assert is_valid_cups(value) is valid
    if valid:
        assert is_valid_cups(normalize_cups(value))


def test_fragmented_cups_on_label_row_takes_precedence_over_bank_details():
    words = [
        (0, 130, 605, 151, 611, "(CUPS):"),
        (0, 162, 605, 169, 611, "ES"),
        (0, 170, 605, 182, 611, "1234"),
        (0, 183, 605, 196, 611, "1234"),
        (0, 198, 605, 211, 611, "5678"),
        (0, 213, 605, 226, 611, "9012"),
        (0, 228, 605, 237, 611, "JY"),
        (0, 25, 625, 45, 631, "IBAN:"),
        (0, 162, 625, 280, 631, "ES001234567890123456"),
    ]
    result = extract_from_text("(CUPS):\nIBAN: ES001234567890123456", words)
    assert result["cups"] == "ES1234123456789012JY"


@pytest.mark.parametrize("text", [
    "CUPS: ES1234123456789012XY\nOtro código: ES0987543210987654ZF",
    "CUPS: ES1234123456789012JY\nCUPS: ES0987543210987654ZF",
    "IBAN: ES001234567890123456",
])
def test_invalid_or_ambiguous_cups_is_left_for_review(text):
    result = extract_from_text(text)
    assert result["cups"] is None
    assert any(issue["field"] == "cups" for issue in result["data_quality"]["issues"])
