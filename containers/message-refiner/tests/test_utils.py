import pytest
from app.utils import _generate_clinical_xpaths
from app.utils import create_clinical_xpaths
from app.utils import load_section_loincs


def test_generate_clinical_xpaths():
    """
    Confirms that xpaths can be generated for sample codes.
    """
    system = "http://loinc.org"
    codes = ["76078-5", "76080-1"]
    expected_output = [
        ".//*[local-name()='entry'][.//*[@code='76078-5' and @codeSystemName='loinc.org']]",
        ".//*[local-name()='entry'][.//*[@code='76080-1' and @codeSystemName='loinc.org']]",
    ]
    output = _generate_clinical_xpaths(system, codes)
    assert output == expected_output


def test_generate_clinical_xpaths_unknown_system():
    """
    Confirms error is generated if system is not recognized.
    """
    system = "http://unknown.org"
    codes = ["A01", "B02"]
    with pytest.raises(KeyError) as exc_info:
        _generate_clinical_xpaths(system, codes)
    assert (
        str(exc_info.value)
        == "'http://unknown.org not a recognized clinical service system.'"
    )


def test_create_clinical_xpaths():
    """
    Confirms dynamic xpaths generated from clinical_service list
    """
    clinical_services_list = [
        {"lrtc": [{"codes": ["76078-5", "76080-1"], "system": "http://loinc.org"}]}
    ]
    expected_xpaths = [
        ".//*[local-name()='entry'][.//*[@code='76078-5' and @codeSystemName='loinc.org']]",
        ".//*[local-name()='entry'][.//*[@code='76080-1' and @codeSystemName='loinc.org']]",
    ]
    actual_xpaths = create_clinical_xpaths(clinical_services_list)
    assert actual_xpaths == expected_xpaths


def test_load_section_loincs():
    """
    Confirms that a dictionary of loinc data can be transformed into a list
    and that a dictionary of required sections can be generated.
    """
    loinc_json = {
        "29762-2": {
            "minimal_fields": [
                "Social History",
                "2.16.840.1.113883.10.20.22.2.17",
                "2015-08-01",
                "Social History",
            ],
            "required": True,
        },
        "11369-6": {
            "minimal_fields": [
                "History of Immunizations",
                "2.16.840.1.113883.10.20.22.4.52",
                "2015-08-01",
                "Immunizations",
            ],
            "required": False,
        },
    }
    expected_section_loincs = ["29762-2", "11369-6"]
    expected_section_details = {
        "29762-2": [
            "Social History",
            "2.16.840.1.113883.10.20.22.2.17",
            "2015-08-01",
            "Social History",
        ]
    }
    section_loincs, section_details = load_section_loincs(loinc_json)
    assert section_loincs == expected_section_loincs
    assert section_details == expected_section_details
