import copy
import json
import pathlib
from unittest import mock

import pytest
from app.main import app
from app.utils import _extract_countries_from_resource
from app.utils import _standardize_date
from app.utils import _standardize_phones_in_resource
from app.utils import _validate_date
from app.utils import BaseFhirGeocodeClient
from app.utils import CensusFhirGeocodeClient
from app.utils import CensusGeocodeClient
from app.utils import GeocodeResult
from app.utils import read_json_from_assets
from app.utils import SmartyFhirGeocodeClient
from app.utils import SmartyGeocodeClient
from app.utils import standardize_country_code
from app.utils import standardize_name
from app.utils import standardize_phone
from app.utils import standardize_phones_in_bundle
from fastapi.testclient import TestClient
from smartystreets_python_sdk.us_street.candidate import Candidate
from smartystreets_python_sdk.us_street.components import Components
from smartystreets_python_sdk.us_street.metadata import Metadata

client = TestClient(app)


@pytest.fixture
def single_patient_bundle():
    return read_json_from_assets("single_patient_bundle.json")


def test_health_check():
    actual_response = client.get("/")
    assert actual_response.status_code == 200
    assert actual_response.json() == {
        "status": "OK",
    }


def test_standardize_name():
    # Basic case of input string
    raw_text = " 12 dIBbs is ReaLLy KEWL !@#$ 34"
    assert (
        standardize_name(raw_text, trim=True, case="lower", remove_numbers=False)
        == "12 dibbs is really kewl  34"
    )
    assert (
        standardize_name(raw_text, trim=True, remove_numbers=True, case="title")
        == "Dibbs Is Really Kewl"
    )
    assert (
        standardize_name(raw_text, trim=False, remove_numbers=True, case="title")
        == "  Dibbs Is Really Kewl  "
    )
    # Now check that it handles list inputs
    names = ["Johnny T. Walker", " Paul bunYAN", "J;R;R;tOlK.iE87n 999"]
    assert standardize_name(names, trim=True, remove_numbers=False) == [
        "JOHNNY T WALKER",
        "PAUL BUNYAN",
        "JRRTOLKIE87N 999",
    ]


@pytest.mark.parametrize(
    "input_date, format_string, future, expected",
    [
        ("1977-11-21", None, False, "1977-11-21"),
        ("1980-01-31", None, False, "1980-01-31"),
        ("1977/11/21", "%Y/%m/%d", False, "1977-11-21"),
        ("1980/01/31", "%Y/%m/%d", False, "1980-01-31"),
        ("01/1980/31", "%m/%Y/%d", False, "1980-01-31"),
        ("11-1977-21", "%m-%Y-%d", False, "1977-11-21"),
    ],
)
def test_standardize_date(input_date, format_string, future, expected):
    if format_string:
        assert _standardize_date(input_date, format_string, future) == expected
    else:
        assert _standardize_date(input_date, future=future) == expected


def test_standardize_date_invalid():
    with pytest.raises(ValueError) as e:
        _standardize_date("blah")
    assert "Invalid date format or missing components in date: blah" in str(e.value)


def test_standardize_date_format_mismatch():
    with pytest.raises(ValueError) as e:
        _standardize_date("abc-def-ghi", "%Y-%m-%d")
    assert "Invalid date format supplied:" in str(e.value)

    with pytest.raises(ValueError) as e:
        _standardize_date("1980-01-31", "%H:%M:%S")
    assert "Invalid date format or missing components in date:" in str(e.value)


@pytest.mark.parametrize(
    "year, month, day, allow_future, expected",
    [
        ("1980", "10", "15", False, True),
        ("3030", "10", "15", False, True),
        ("3030", "10", "15", True, False),
        ("2005", "15", "10", False, False),
        ("2005", "02", "30", False, False),
    ],
)
def test_validate_date(year, month, day, allow_future, expected):
    assert _validate_date(year, month, day, allow_future) == expected


def test_standardize_country_code():
    assert standardize_country_code("US") == "US"
    assert standardize_country_code("USA") == "US"
    assert standardize_country_code("United States of America") == "US"
    assert standardize_country_code("United states ") == "US"
    assert standardize_country_code("US", "alpha_3") == "USA"
    assert standardize_country_code("USA", "numeric") == "840"

    # Edge case testing: nonsense code and empty string
    assert standardize_country_code("zzz") is None
    assert standardize_country_code("") is None


def test_standardize_phone():
    # Working examples of "real" numbers
    assert standardize_phone("555-654-9876") == "+15556549876"
    assert standardize_phone("555 654 9876") == "+15556549876"
    # Now supply country information
    assert standardize_phone("123.234.6789", ["US"]) == "+11232346789"
    assert standardize_phone("798.612.3456", ["GB"]) == "+447986123456"
    # Now do it as a list
    assert standardize_phone(["555-654-1234", "919876543210"], countries=["IN"]) == [
        "+915556541234",
        "+919876543210",
    ]
    # Make sure we catch edge cases and bad inputs
    assert standardize_phone("") == ""
    assert standardize_phone(" ") == ""
    assert standardize_phone("gibberish") == ""
    assert standardize_phone("1234567890987654321") == ""
    assert standardize_phone("123") == ""


def test_standardize_phones():
    raw_bundle = json.load(
        open(
            pathlib.Path(__file__).parent.parent / "assets" / "test_patient_bundle.json"
        )
    )

    # Case where we pass in a whole FHIR bundle
    standardized_bundle = copy.deepcopy(raw_bundle.copy())
    patient = standardized_bundle["entry"][1]["resource"]
    patient["telecom"][0]["value"] = "+11234567890"
    assert standardize_phones_in_bundle(raw_bundle) == standardized_bundle

    # Case where we pass in a whole FHIR bundle and do not overwrite the data
    standardized_bundle = copy.deepcopy(raw_bundle.copy())
    patient = standardized_bundle["entry"][1]["resource"]
    patient["telecom"][0]["value"] = "+11234567890"
    assert (
        standardize_phones_in_bundle(raw_bundle, overwrite=False) == standardized_bundle
    )

    # Case where we provide only a single resource
    patient_resource = raw_bundle["entry"][1]["resource"]
    standardized_patient = copy.deepcopy(patient_resource)
    standardized_patient["telecom"][0]["value"] = "+11234567890"
    assert standardize_phones_in_bundle(patient_resource) == standardized_patient

    # Case where we provide only a single resource and do not overwrite the data
    patient_resource = raw_bundle["entry"][1]["resource"]
    standardized_patient = copy.deepcopy(patient_resource)
    standardized_patient["telecom"][0]["value"] = "+11234567890"
    assert (
        standardize_phones_in_bundle(patient_resource, overwrite=False)
        == standardized_patient
    )

    # Case where the input data has no country information in the address
    patient_resource = raw_bundle["entry"][1]["resource"]
    patient_resource.get("address")[0].pop("country")
    assert patient_resource.get("address")[0].get("country") is None
    standardized_patient = copy.deepcopy(patient_resource)
    standardized_patient["telecom"][0]["value"] = "+11234567890"
    assert standardize_phones_in_bundle(patient_resource) == standardized_patient

    # Case where the input data has no country information in the address and we do not
    # overwrite the data
    patient_resource = raw_bundle["entry"][1]["resource"]
    assert patient_resource.get("address")[0].get("country") is None
    standardized_patient = copy.deepcopy(patient_resource)
    standardized_patient["telecom"][0]["value"] = "+11234567890"
    assert (
        standardize_phones_in_bundle(patient_resource, overwrite=False)
        == standardized_patient
    )


def test_standardize_phones_in_resource():
    raw_bundle = json.load(
        open(
            pathlib.Path(__file__).parent.parent / "assets" / "test_patient_bundle.json"
        )
    )
    patient_resource = raw_bundle["entry"][1]["resource"]
    standardized_patient = copy.deepcopy(patient_resource)
    standardized_patient["telecom"][0]["value"] = "+11234567890"
    assert _standardize_phones_in_resource(patient_resource) == standardized_patient


def test_extract_countries_from_resource():
    raw_bundle = json.load(
        open(
            pathlib.Path(__file__).parent.parent / "assets" / "test_patient_bundle.json"
        )
    )
    patient = raw_bundle["entry"][1].get("resource")
    patient["address"].append(patient["address"][0])
    patient["address"].append(patient["address"][0])
    assert [country for country in _extract_countries_from_resource(patient)] == [
        "US"
    ] * 3
    assert [
        country for country in _extract_countries_from_resource(patient, "alpha_3")
    ] == ["USA"] * 3
    assert [
        country for country in _extract_countries_from_resource(patient, "numeric")
    ] == ["840"] * 3


@pytest.fixture
def expected_smarty_geocode_result():
    return GeocodeResult(
        line=["1428 Post Aly"],
        city="Seattle",
        state="WA",
        lat=47.608479,
        lng=-122.340202,
        county_fips="53033",
        county_name="King",
        postal_code="98101",
        precision="Rooftop",
    )


@pytest.fixture
def smarty_geocode_client():
    smarty_auth_id = mock.Mock()
    smarty_auth_token = mock.Mock()
    return SmartyGeocodeClient(smarty_auth_id, smarty_auth_token)


@pytest.fixture
def mock_smarty_candidate():
    candidate = Candidate({})
    candidate.delivery_line_1 = "1428 Post Aly"
    candidate.components = Components(
        {
            "primary_number": "1428",
            "street_name": "Post",
            "street_suffix": "Aly",
            "city_name": "Seattle",
            "state_abbreviation": "WA",
            "zipcode": "98101",
            "plus4_code": "2034",
        }
    )
    candidate.metadata = Metadata(
        {
            "latitude": 47.608479,
            "longitude": -122.340202,
            "county_fips": "53033",
            "county_name": "King",
            "precision": "Rooftop",
        }
    )
    return candidate


@pytest.fixture
def geocode_input_dict():
    return {
        "street": "1428 Post Aly",
        "city": "Seattle",
        "state": "WA",
        "zip": "98101",
    }


@pytest.fixture
def geocode_input_incomplete_dict():
    return {
        "street": "1428 Post Aly",
    }


@pytest.fixture
def geocode_input_malformed_dict():
    return {
        "street": "!#%&*!",
        "city": "1428",
        "state": "Aly",
        "zip": "00000",
    }


def test_smarty_parse_result_success(
    mock_smarty_candidate, expected_smarty_geocode_result
):
    candidate = mock_smarty_candidate

    lookup = mock.Mock()
    lookup.result = [candidate]
    encoded_result = SmartyGeocodeClient._parse_smarty_result(lookup)

    assert encoded_result == expected_smarty_geocode_result


def test_smarty_parse_result_failure():
    # no result from the API
    lookup_no_result = mock.Mock()
    lookup_no_result.result = None
    assert SmartyGeocodeClient._parse_smarty_result(lookup_no_result) is None

    # incomplete data in the result
    lookup_incomplete = mock.Mock()
    candidate_incomplete = Candidate({})
    candidate_incomplete.delivery_line_1 = "1428 Post Aly"
    lookup_incomplete.result = [candidate_incomplete]

    assert SmartyGeocodeClient._parse_smarty_result(lookup_incomplete) is None


def test_smarty_blank_geocode_inputs(smarty_geocode_client):
    assert smarty_geocode_client.client is not None

    # test geocode_from_str with empty string
    with pytest.raises(ValueError) as e:
        smarty_geocode_client.geocode_from_str("")
    assert "Address must include street number and name at a minimum" in str(e.value)

    # test geocode_from_dict with empty dict
    with pytest.raises(ValueError) as e:
        smarty_geocode_client.geocode_from_dict({})
    assert "Address must include street number and name at a minimum" in str(e.value)


def test_smarty_geocode_from_str(
    smarty_geocode_client, mock_smarty_candidate, expected_smarty_geocode_result
):
    assert smarty_geocode_client.client is not None

    with mock.patch.object(
        smarty_geocode_client.client, "send_lookup"
    ) as mock_send_lookup:
        # provide a function that adds results to the existing object
        def fill_in_result(*args, **kwargs):
            args[0].result = [mock_smarty_candidate]

        mock_send_lookup.side_effect = fill_in_result

        assert expected_smarty_geocode_result == smarty_geocode_client.geocode_from_str(
            "1428 Post Aly Seattle WA 98101"
        )
        mock_send_lookup.assert_called()


def test_smarty_geocode_from_dict(
    smarty_geocode_client,
    mock_smarty_candidate,
    expected_smarty_geocode_result,
    geocode_input_dict,
):
    assert smarty_geocode_client.client is not None

    with mock.patch.object(
        smarty_geocode_client.client, "send_lookup"
    ) as mock_send_lookup:
        # provide a function that adds results to the existing object
        def fill_in_result(*args, **kwargs):
            args[0].result = [mock_smarty_candidate]

        mock_send_lookup.side_effect = fill_in_result

        assert (
            expected_smarty_geocode_result
            == smarty_geocode_client.geocode_from_dict(geocode_input_dict)
        )
        mock_send_lookup.assert_called()


@pytest.fixture
def census_api_response():
    with open(
        pathlib.Path(__file__).parent / "assets" / "censusResponse.json", "r"
    ) as file:
        return json.load(file)


@pytest.fixture
def expected_census_geocode_result():
    return GeocodeResult(
        line=["1428 POST ALY"],
        city="SEATTLE",
        state="WA",
        postal_code="98101",
        county_fips="53033",
        lat=47.60793195443486,
        lng=-122.33986641487036,
        district=None,
        country=None,
        county_name="King",
        precision=None,
        geoid="530330081012004",
        census_tract="81.01",
        census_block="2004",
    )


@pytest.fixture
def census_client():
    return CensusGeocodeClient()


@pytest.fixture
def mock_call_census_api(census_api_response):
    with mock.patch.object(
        CensusGeocodeClient, "_call_census_api", return_value=census_api_response
    ):
        yield


def test_census_direct_call_to_mocked_method(census_api_response):
    with mock.patch.object(
        CensusGeocodeClient, "_call_census_api", return_value=census_api_response
    ) as mocked_method:
        census_client = CensusGeocodeClient()
        result = census_client._call_census_api("dummy_url")
        assert result == census_api_response
        mocked_method.assert_called_once_with("dummy_url")


def test_census_parse_results(census_api_response, expected_census_geocode_result):
    parsed_result = CensusGeocodeClient._parse_census_result(
        census_api_response["result"]
    )
    assert parsed_result == expected_census_geocode_result


def test_parse_census_result_failure(census_api_response):
    # Simulate a response with no address matches
    census_api_response["result"]["addressMatches"] = []

    # Call the parsing method with the simulated response
    result = CensusGeocodeClient._parse_census_result(census_api_response["result"])

    # Assert that the result is None, as there are no address matches
    assert result is None


def test_census_geocode_from_str(
    census_client, census_api_response, expected_census_geocode_result
):
    # mock _call_census_api to return the expected response
    with mock.patch.object(
        CensusGeocodeClient,
        "_call_census_api",
        return_value=census_api_response["result"],
    ):
        result = census_client.geocode_from_str("1428 Post Aly Seattle WA 98101")
        assert result == expected_census_geocode_result

        incomplete_result = census_client.geocode_from_str("1428 Post Aly")
        assert incomplete_result is None or isinstance(incomplete_result, GeocodeResult)

    # test with an empty string
    with pytest.raises(ValueError):
        census_client.geocode_from_str("")

    # test with a malformed string
    with pytest.raises(ValueError):
        census_client.geocode_from_str("@#%&*!")


def test_census_geocode_from_dict(
    census_client,
    census_api_response,
    expected_census_geocode_result,
    geocode_input_dict,
    geocode_input_incomplete_dict,
    geocode_input_malformed_dict,
):
    # mock _call_census_api to return the expected response
    with mock.patch.object(
        CensusGeocodeClient,
        "_call_census_api",
        return_value=census_api_response["result"],
    ):
        result = census_client.geocode_from_dict(geocode_input_dict)
        assert result == expected_census_geocode_result

        incomplete_result = census_client.geocode_from_dict(
            geocode_input_incomplete_dict
        )
        assert incomplete_result is None or isinstance(incomplete_result, GeocodeResult)

    # test with an empty dict
    with pytest.raises(ValueError):
        census_client.geocode_from_dict({})

    # test with a malformed dict
    with pytest.raises(ValueError):
        census_client.geocode_from_dict(geocode_input_malformed_dict)


@pytest.fixture
def patient_bundle():
    with open(
        pathlib.Path(__file__).parent / "assets" / "patientBundle.json", "r"
    ) as file:
        return json.load(file)


@pytest.fixture
def patient_bundle_extension():
    with open(
        pathlib.Path(__file__).parent / "assets" / "patientBundleExtension.json", "r"
    ) as file:
        return json.load(file)


@pytest.fixture
def smarty_fhir_geocode_client():
    smarty_auth_id = mock.Mock()
    smarty_auth_token = mock.Mock()
    return SmartyFhirGeocodeClient(smarty_auth_id, smarty_auth_token)


def _get_patient_from_bundle(bundle):
    return bundle["entry"][1]["resource"]


def _update_patient_address(
    patient: dict, geocoded_response: GeocodeResult, context: str = "smarty"
) -> None:
    """
    Updates the address of a patient resource with geocoded address details.
    Context can be either 'smarty' or 'census' to handle specific extensions.

    :param patient: The patient resource (dict) whose address will be updated.
    :param geocoded_response: The geocoded address data (GeocodeResult).
    :param context: The context of geocoding ('smarty' or 'census').
    :return: None
    """
    address = patient.get("address", [{}])[0]
    address["city"] = geocoded_response.city
    address["state"] = geocoded_response.state
    address["postalCode"] = geocoded_response.postal_code

    # add geolocation extensions
    BaseFhirGeocodeClient._store_lat_long_extension(
        address, geocoded_response.lat, geocoded_response.lng
    )

    # for Census context, add census tract extension and potentially additional logic
    if context == "census":
        # add specific logic here from _extract_address if needed
        BaseFhirGeocodeClient._store_census_tract_extension(
            address, geocoded_response.census_tract
        )


def test_store_lat_long_fhir(patient_bundle, expected_smarty_geocode_result):
    # extract the patient from the bundle
    patient = patient_bundle["entry"][1]["resource"]
    address = patient.get("address", [])[0]

    # store latitude and longitude using the method
    BaseFhirGeocodeClient._store_lat_long_extension(
        address, expected_smarty_geocode_result.lat, expected_smarty_geocode_result.lng
    )

    # assert that the extension field is added to the address
    assert "extension" in address, "No extension field found in the address"

    # find the geolocation extension
    geo_extension = next(
        (ext for ext in address["extension"] if "geolocation" in ext.get("url", "")),
        None,
    )
    assert geo_extension is not None, "Geolocation extension not found"

    # extract latitude and longitude extensions
    lat_extension = next(
        ext
        for ext in geo_extension.get("extension", [])
        if ext.get("url") == "latitude"
    )
    long_extension = next(
        ext
        for ext in geo_extension.get("extension", [])
        if ext.get("url") == "longitude"
    )

    # assert that latitude and longitude are stored correctly
    assert (
        lat_extension.get("valueDecimal") == expected_smarty_geocode_result.lat
    ), "Latitude value mismatch"
    assert (
        long_extension.get("valueDecimal") == expected_smarty_geocode_result.lng
    ), "Longitude value mismatch"


def test_geocode_resource_overwrite_false(
    smarty_fhir_geocode_client, expected_smarty_geocode_result, patient_bundle
):
    patient = _get_patient_from_bundle(patient_bundle)
    standardized_patient = copy.deepcopy(patient)
    _update_patient_address(
        standardized_patient, expected_smarty_geocode_result, context="smarty"
    )

    with mock.patch.object(
        smarty_fhir_geocode_client.geocode_client,
        "geocode_from_str",
        return_value=expected_smarty_geocode_result,
    ):
        returned_patient = smarty_fhir_geocode_client.geocode_resource(
            patient, overwrite=False
        )
        assert standardized_patient == returned_patient
        assert returned_patient != patient


def test_geocode_bundle(
    smarty_fhir_geocode_client, expected_smarty_geocode_result, patient_bundle
):
    standardized_bundle = copy.deepcopy(patient_bundle)

    # update the standardized bundle using the utility function
    for entry in standardized_bundle.get("entry", []):
        patient = entry.get("resource")
        if patient and patient.get("resourceType") == "Patient":
            _update_patient_address(
                patient, expected_smarty_geocode_result, context="smarty"
            )

    with mock.patch.object(
        smarty_fhir_geocode_client.geocode_client,
        "geocode_from_str",
        return_value=expected_smarty_geocode_result,
    ):
        returned_bundle = smarty_fhir_geocode_client.geocode_bundle(
            patient_bundle, overwrite=False
        )

        assert standardized_bundle == returned_bundle
        assert patient_bundle != standardized_bundle
        smarty_fhir_geocode_client.geocode_client.geocode_from_str.assert_called()


@pytest.fixture
def census_fhir_client():
    return CensusFhirGeocodeClient()


def test_geocode_resource_census_fhir(
    patient_bundle,
    patient_bundle_extension,
    expected_census_geocode_result,
    census_fhir_client,
):
    assert census_fhir_client is not None

    # case 1 and case 2: testing with patient_bundle
    patient = _get_patient_from_bundle(patient_bundle)
    standardized_patient = copy.deepcopy(patient)
    _update_patient_address(
        standardized_patient, expected_census_geocode_result, context="census"
    )

    with mock.patch.object(
        census_fhir_client._CensusFhirGeocodeClient__client,
        "geocode_from_dict",
        return_value=expected_census_geocode_result,
    ):
        # test with overwrite=False
        returned_patient = census_fhir_client.geocode_resource(patient, overwrite=False)
        assert standardized_patient == returned_patient
        assert returned_patient.get("address") != patient.get("address")
        assert returned_patient.get("address")[0].get("line") == ["1428 Post Aly"]

        # test with overwrite=True
        returned_patient = census_fhir_client.geocode_resource(patient, overwrite=True)
        assert returned_patient["address"][0].get("line") == ["1428 Post Aly"]
        assert returned_patient == patient

    # case 3: testing with patient_bundle_extension (has existing extension)
    patient = _get_patient_from_bundle(patient_bundle_extension)
    standardized_patient = copy.deepcopy(patient)
    _update_patient_address(
        standardized_patient, expected_census_geocode_result, context="census"
    )

    with mock.patch.object(
        census_fhir_client._CensusFhirGeocodeClient__client,
        "geocode_from_dict",
        return_value=expected_census_geocode_result,
    ):
        returned_patient = census_fhir_client.geocode_resource(patient, overwrite=True)

        assert returned_patient == standardized_patient
        assert returned_patient.get("address")[0].get("_line")[0].get("extension")[
            0
        ] == {"existing_url": "existing_extension"}

        # check if second element of '_line' array exists and is not None
        second_line_element = returned_patient.get("address")[0].get("_line")[1]
        if second_line_element:
            assert second_line_element.get("extension")[0] is not None


def test_geocode_bundle_census_fhir(
    patient_bundle, expected_census_geocode_result, census_fhir_client
):
    assert census_fhir_client is not None

    standardized_bundle = copy.deepcopy(patient_bundle)
    patient = _get_patient_from_bundle(standardized_bundle)
    _update_patient_address(patient, expected_census_geocode_result, context="census")

    returned_bundle = census_fhir_client.geocode_bundle(patient_bundle, overwrite=False)
    assert standardized_bundle == returned_bundle
    assert patient_bundle != standardized_bundle
