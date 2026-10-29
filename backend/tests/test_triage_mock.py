import pytest

from triage.mock import clean_text


@pytest.mark.parametrize("raw,expected,informative", [
    ("UNIT NOTED ROTOR WAS SNAPPED. Serial Number: 1JAP5JK8", "UNIT NOTED ROTOR WAS SNAPPED", True),
    ("NO POWER ON STARTUP PO#=4531756794 SN:80145369", "NO POWER ON STARTUP", True),
    ("'No reason given - FQA Serial Number: 1JAP5JK8 Ship/End Customer PO: 140827129", "No reason given - FQA", False),
    ("Serial Number: 1JBA1FJ5", "", False),
    ("SERIAL NUMBER= 96537025 FAILURE INFORMATION=CUSTOMER DID NOT IDENTIFY FAULT", None, False),
])
def test_clean_text(raw, expected, informative):
    text, inf = clean_text(raw)
    if expected is not None:
        assert text == expected
    assert inf is informative
