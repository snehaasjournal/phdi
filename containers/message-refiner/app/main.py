from pathlib import Path
from typing import Annotated

import httpx
from dibbs.base_service import BaseService
from fastapi import Query
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from lxml import etree as ET

from app.config import get_settings
from app.models import RefineECRResponse
from app.utils import _generate_clinical_xpaths
from app.utils import read_json_from_assets

settings = get_settings()
TCR_ENDPOINT = f"{settings['tcr_url']}/get-value-sets?condition_code="


# Instantiate FastAPI via DIBBs' BaseService class
app = BaseService(
    service_name="Message Refiner",
    service_path="/message-refiner",
    description_path=Path(__file__).parent.parent / "description.md",
    include_health_check_endpoint=False,
).start()


# /ecr endpoint request examples
refine_ecr_request_examples = read_json_from_assets("sample_refine_ecr_request.json")
refine_ecr_response_examples = read_json_from_assets("sample_refine_ecr_response.json")


def custom_openapi():
    """
    This customizes the FastAPI response to allow example requests given that the
    raw Request cannot have annotations.
    """
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    path = openapi_schema["paths"]["/ecr"]["post"]
    path["requestBody"] = {
        "content": {
            "application/xml": {
                "schema": {"type": "Raw eCR XML payload"},
                "examples": refine_ecr_request_examples,
            }
        }
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
async def health_check():
    """
    Check service status. If an HTTP 200 status code is returned along with
    '{"status": "OK"}' then the refiner service is available and running
    properly.
    """
    return {"status": "OK"}


@app.get("/example-collection")
async def get_uat_collection() -> FileResponse:
    """
    Fetches a Postman Collection of sample requests designed for UAT.
    The Collection is a JSON-exported file consisting of five GET and POST
    requests to endpoints of the publicly available dibbs.cloud server.
    The requests showcase the functionality of various aspects of the TCR
    and the message refine.
    """
    uat_collection_path = (
        Path(__file__).parent.parent
        / "assets"
        / "Message_Refiner_UAT.postman_collection.json"
    )
    return FileResponse(uat_collection_path)


@app.post(
    "/ecr",
    response_model=RefineECRResponse,
    status_code=200,
    responses=refine_ecr_response_examples,
)
async def refine_ecr(
    refiner_input: Request,
    sections_to_include: Annotated[
        str | None,
        Query(
            description="""The sections of an ECR to include in the refined message.
            Multiples can be delimited by a comma. Valid LOINC codes for sections are:\n
            10164-2: history of present illness\n
            11369-6: history of immunization narrative\n
            29549-3: medications administered\n
            18776-5: plan of care note\n
            11450-4: problem list - reported\n
            29299-5: reason for visit\n
            30954-2: relevant diagnostic tests/laboratory data narrative\n
            29762-2: social history narrative\n
            46240-8:  history of hospitalizations+outpatient visits narrative\n
            """
        ),
    ] = None,
    conditions_to_include: Annotated[
        str | None,
        Query(
            description="The SNOMED condition codes to use to search for relevant clinical services in the ECR."
            + " Multiples can be delimited by a comma."
        ),
    ] = None,
) -> Response:
    """
    Refines an incoming XML ECR message based on sections to include and/or trigger code
    conditions to include, based on the parameters included in the endpoint.

    The return will be a formatted, refined XML, limited to just the data specified.

    :param refiner_input: The request object containing the XML input.
    :param sections_to_include: The fields to include in the refined message.
    :param conditions_to_include: The SNOMED condition codes to use to search for
    relevant clinical services in the ECR.
    :return: The RefineECRResponse, the refined XML as a string.
    """
    data = await refiner_input.body()

    validated_message, error_message = validate_message(data)
    if error_message:
        return Response(content=error_message, status_code=status.HTTP_400_BAD_REQUEST)

    sections = None
    if sections_to_include:
        sections, error_message = validate_sections_to_include(sections_to_include)
        if error_message:
            return Response(
                content=error_message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

    clinical_services_xpaths = None
    if conditions_to_include:
        responses = await get_clinical_services(conditions_to_include)
        # confirm all API responses were 200
        if set([response.status_code for response in responses]) != {200}:
            error_message = ";".join(
                [str(response) for response in responses if response.status_code != 200]
            )
            return Response(
                content=error_message, status_code=status.HTTP_502_BAD_GATEWAY
            )
        clinical_services = [response.json() for response in responses]
        clinical_services_xpaths = create_clinical_xpaths(clinical_services)

    data = refine(validated_message, sections, clinical_services_xpaths)

    return Response(content=data, media_type="application/xml")


def validate_sections_to_include(sections_to_include: str | None) -> tuple[list, str]:
    """
    Validates the sections to include in the refined message and returns them as a list
    of corresponding LOINC codes.

    :param sections_to_include: The sections to include in the refined message.
    :raises ValueError: When at least one of the sections_to_inlcude is invalid.
    :return: A tuple that includes the sections to include in the refined message as a
    list of LOINC codes corresponding to the sections and an error message. If there is
    no error in validating the sections to include, the error message will be an empty
    string.
    """
    section_LOINCs = [
        "10164-2",  # history of present illness
        "11369-6",  # history of immunization narrative
        "29549-3",  # medications administered
        "18776-5",  # plan of care note
        "11450-4",  # problem list - reported
        "29299-5",  # reason for visit
        "30954-2",  # relevant diagnostic tests/laboratory data narrative
        "29762-2",  # social history narrative
        "46240-8",  # history of hospitalizations+outpatient visits narrative
    ]

    if sections_to_include in [None, ""]:
        return (None, "")

    section_loincs = []
    sections = sections_to_include.split(",")
    for section in sections:
        if section not in section_LOINCs:
            error_message = f"{section} is invalid. Please provide a valid section."
            return (section_loincs, error_message)
        section_loincs.append(section)

    return (section_loincs, "")


async def get_clinical_services(condition_codes: str) -> list[dict]:
    """
    This a function that loops through the provided condition codes. For each
    condition code provided, it calls the trigger-code-reference service to get
    the API response for that condition.

    :param condition_codes: SNOMED condition codes to look up in TCR service
    :return: List of API responses to check
    """
    clinical_services_list = []
    conditions_list = condition_codes.split(",")
    async with httpx.AsyncClient() as client:
        for condition in conditions_list:
            response = await client.get(TCR_ENDPOINT + condition)
            clinical_services_list.append(response)
    return clinical_services_list


def create_clinical_xpaths(clinical_services_list: list[dict]) -> list[str]:
    """
    This function loops through each of those clinical service codes and their
    system to create a list of all possible xpath queries.
    :param clinical_services_list: List of clinical_service dictionaries.
    :return: List of xpath queries to check.
    """
    clinical_services_xpaths = []
    for clinical_services in clinical_services_list:
        for system, entries in clinical_services.items():
            for entry in entries:
                system = entry.get("system")
                xpaths = _generate_clinical_xpaths(system, entry.get("codes"))
                clinical_services_xpaths.extend(xpaths)
    return clinical_services_xpaths


def refine(
    validated_message: bytes,
    sections_to_include: list = None,
    clinical_services: list = None,
) -> str:
    """
    Refines an incoming XML message based on the sections to include and/or
    the clinical services found based on inputted section LOINC codes or
    condition SNOMED codes. This will then loop through the dynamic XPaths to
    create an XPath to refine the XML.

    :param validated_message: The XML input.
    :param sections_to_include: The sections to include in the refined message.
    :param clinical_services_xpaths: clinical service XPaths to include in the
    refined message.
    :return: The refined message.
    """
    header = select_message_header(validated_message)

    # Set up XPath expressions
    namespaces = {"hl7": "urn:hl7-org:v3"}
    if sections_to_include:
        sections_xpaths = " or ".join(
            [f"@code='{section}'" for section in sections_to_include]
        )
        sections_xpath_expression = (
            f"//*[local-name()='section'][hl7:code[{sections_xpaths}]]"
        )

    if clinical_services:
        services_xpath_expression = " | ".join(clinical_services)

    # both are handled slightly differently
    if sections_to_include and clinical_services:
        elements = []
        sections = validated_message.xpath(
            sections_xpath_expression, namespaces=namespaces
        )
        for section in sections:
            condition_elements = section.xpath(
                services_xpath_expression, namespaces=namespaces
            )
            if condition_elements:
                elements.extend(condition_elements)
        return add_root_element(header, elements)

    if sections_to_include:
        xpath_expression = sections_xpath_expression
    elif clinical_services:
        xpath_expression = services_xpath_expression
    else:
        xpath_expression = "//*[local-name()='section']"
    elements = validated_message.xpath(xpath_expression, namespaces=namespaces)
    return add_root_element(header, elements)


def add_root_element(header: bytes, elements: list) -> str:
    """
    This helper function sets up and creates a new root element for the XML
    by using a combination of a direct namespace uri and nsmap to ensure that
    the default namespaces are set correctly.
    :param header: The header section of the XML.
    :param elements: List of refined elements found in XML.
    :return: The full refined XML, formatted as a string.
    """
    namespace = "urn:hl7-org:v3"
    nsmap = {
        None: namespace,
        "cda": namespace,
        "sdtc": "urn:hl7-org:sdtc",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    }
    # creating the root element with our uri namespace and nsmap
    refined_message_root = ET.Element(f"{{{namespace}}}ClinicalDocument", nsmap=nsmap)
    for h in header:
        refined_message_root.append(h)
    # creating the component element and structuredBody element with the same namespace
    # and adding them to the new root
    main_component = ET.SubElement(refined_message_root, f"{{{namespace}}}component")
    structuredBody = ET.SubElement(main_component, f"{{{namespace}}}structuredBody")

    # Append the filtered elements to the new root and use the uri namespace
    for element in elements:
        section_component = ET.SubElement(structuredBody, f"{{{namespace}}}component")
        section_component.append(element)

    # Create a new ElementTree with the result root
    refined_message = ET.ElementTree(refined_message_root)
    return ET.tostring(refined_message, encoding="unicode")


def select_message_header(raw_message: bytes) -> bytes:
    """
    Selects the header of an incoming message.

    :param raw_message: The XML input.
    :return: The header section of the XML.
    """
    HEADER_SECTIONS = [
        "realmCode",
        "typeId",
        "templateId",
        "id",
        "code",
        "title",
        "effectiveTime",
        "confidentialityCode",
        "languageCode",
        "setId",
        "versionNumber",
        "recordTarget",
        "author",
        "custodian",
        "componentOf",
    ]

    # Set up XPath expression
    namespaces = {"hl7": "urn:hl7-org:v3"}
    xpath_expression = " | ".join(
        [f"//hl7:ClinicalDocument/hl7:{section}" for section in HEADER_SECTIONS]
    )
    # Use XPath to find elements matching the expression
    elements = raw_message.xpath(xpath_expression, namespaces=namespaces)

    # Create & set up a new root element for the refined XML
    header = ET.Element(raw_message.tag)

    # Append the filtered elements to the new root
    for element in elements:
        header.append(element)

    return header


def validate_message(raw_message: str) -> tuple[bytes | None, str]:
    """
    Validates that an incoming XML message can be parsed by lxml's etree .

    :param raw_message: The XML input.
    :return: The validation result as a string.
    """
    error_message = ""
    try:
        validated_message = ET.fromstring(raw_message)
        return (validated_message, error_message)
    except ET.XMLSyntaxError as e:
        error_message = f"XMLSyntaxError: {e}"
        return (None, str(error_message))
