import json
import os
from pathlib import Path
from typing import Annotated
from typing import Dict
from typing import Literal
from typing import Optional
from typing import Union

from app.config import get_settings
from app.utils import convert_to_fhir
from app.utils import freeze_parsing_schema
from app.utils import get_credential_manager
from app.utils import get_metadata
from app.utils import get_parsers
from app.utils import load_parsing_schema
from app.utils import read_json_from_assets
from app.utils import search_for_required_values
from fastapi import Body
from fastapi import Response
from fastapi import status
from pydantic import BaseModel
from pydantic import Field
from pydantic import root_validator

from phdi.containers.base_service import BaseService

# Read settings immediately to fail fast in case there are invalid values.
get_settings()

# Instantiate FastAPI via PHDI's BaseService class
app = BaseService(
    service_name="PHDI Message Parser",
    description_path=Path(__file__).parent.parent / "description.md",
).start()

# /parse_message endpoint #
parse_message_request_examples = read_json_from_assets(
    "sample_parse_message_requests.json"
)
raw_parse_message_response_examples = read_json_from_assets(
    "sample_parse_message_responses.json"
)
parse_message_response_examples = {200: raw_parse_message_response_examples}


# Request and response models
class ParseMessageInput(BaseModel):
    """
    The schema for requests to the /extract endpoint.
    """

    message_format: Literal["fhir", "hl7v2", "ecr"] = Field(
        description="The format of the message."
    )
    message_type: Optional[Literal["ecr", "elr", "vxu"]] = Field(
        description="The type of message that values will be extracted from. Required "
        "when 'message_format is not FHIR."
    )
    parsing_schema: Optional[dict] = Field(
        description="A schema describing which fields to extract from the message. This"
        " must be a JSON object with key:value pairs of the form "
        "<my-field>:<FHIR-to-my-field>.",
        default={},
    )
    parsing_schema_name: Optional[str] = Field(
        description="The name of a schema that was previously"
        " loaded in the service to use to extract fields from the message.",
        default="",
    )
    fhir_converter_url: Optional[str] = Field(
        description="The URL of an instance of the PHDI FHIR converter. Required when "
        "the message is not already in FHIR format.",
        default="",
    )
    credential_manager: Optional[Literal["azure", "gcp"]] = Field(
        description="The type of credential manager to use for authentication with a "
        "FHIR converter when conversion to FHIR is required.",
        default=None,
    )
    include_metadata: Optional[Literal["true", "false"]] = Field(
        description="Boolean to include metadata in the response.",
        default=None,
    )
    message: Union[str, dict] = Field(description="The message to be parsed.")

    @root_validator
    def require_message_type_when_not_fhir(cls, values):
        if (
            values.get("message_format") != "fhir"
            and values.get("message_type") is None
        ):
            raise ValueError(
                "When the message format is not FHIR then the message type must be "
                "included."
            )
        return values

    @root_validator
    def prohibit_schema_and_schema_name(cls, values):
        if (
            values.get("parsing_schema") != {}
            and values.get("parsing_schema_name") != ""
        ):
            raise ValueError(
                "Values for both 'parsing_schema' and 'parsing_schema_name' have been "
                "provided. Only one of these values is permited."
            )
        return values

    @root_validator
    def require_schema_or_schema_name(cls, values):
        if (
            values.get("parsing_schema") == {}
            and values.get("parsing_schema_name") == ""
        ):
            raise ValueError(
                "Values for 'parsing_schema' and 'parsing_schema_name' have not been "
                "provided. One, but not both, of these values is required."
            )
        return values


class ParseMessageResponse(BaseModel):
    """
    The schema for responses from the /extract endpoint.
    """

    message: str = Field(
        description="A message describing the result of a request to "
        "the /parse_message endpoint."
    )
    parsed_values: dict = Field(
        description="A set of key:value pairs containing the values extracted from the "
        "message."
    )


@app.post("/parse_message", status_code=200, responses=parse_message_response_examples)
async def parse_message_endpoint(
    input: Annotated[ParseMessageInput, Body(examples=parse_message_request_examples)],
    response: Response,
) -> ParseMessageResponse:
    """
    Extract the desired values from a message. If the message is not already in
    FHIR format, convert it to FHIR first. You can either provide a parsing schema
    or the name of a previously loaded parsing schema.
    """
    # 1. Load schema.
    if input.parsing_schema != {}:
        parsing_schema = freeze_parsing_schema(input.parsing_schema)
    else:
        try:
            parsing_schema = load_parsing_schema(input.parsing_schema_name)
        except FileNotFoundError as error:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return {"message": error.__str__(), "parsed_values": {}}

    # 2. Convert to FHIR, if necessary.
    if input.message_format != "fhir":
        if input.credential_manager is not None:
            input.credential_manager = get_credential_manager(
                credential_manager=input.credential_manager,
                location_url=input.fhir_converter_url,
            )

        search_result = search_for_required_values(dict(input), ["fhir_converter_url"])
        if search_result != "All values were found.":
            response.status_code = status.HTTP_400_BAD_REQUEST
            return {"message": search_result, "parsed_values": {}}

        fhir_converter_response = convert_to_fhir(
            message=input.message,
            message_type=input.message_type,
            fhir_converter_url=input.fhir_converter_url,
            credential_manager=input.credential_manager,
        )
        if fhir_converter_response.status_code == 200:
            input.message = fhir_converter_response.json()["FhirResource"]
        else:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return {
                "message": f"Failed to convert to FHIR: {fhir_converter_response.text}",
                "parsed_values": {},
            }

    # 3. Generate parsers for FHIRpaths specified in schema.
    parsers = get_parsers(parsing_schema)

    # 4. Extract desired fields from message by applying each parser.
    parsed_values = {}
    for field, parser in parsers.items():
        if "secondary_parsers" not in parser:
            value = parser["primary_parser"](input.message)
            if len(value) == 0:
                value = None
            else:
                value = ",".join(map(str, value))
            parsed_values[field] = value
        else:
            inital_values = parser["primary_parser"](input.message)
            values = []
            for initial_value in inital_values:
                value = {}
                for secondary_field, secondary_parser in parser[
                    "secondary_parsers"
                ].items():
                    if len(secondary_parser(initial_value)) == 0:
                        value[secondary_field] = None
                    else:
                        value[secondary_field] = ",".join(
                            map(str, secondary_parser(initial_value))
                        )
                values.append(value)
            parsed_values[field] = values
    if input.include_metadata == "true":
        parsed_values = get_metadata(parsed_values, parsing_schema)
    return {"message": "Parsing succeeded!", "parsed_values": parsed_values}


# /schemas endpoint #
raw_list_schemas_response = read_json_from_assets("sample_list_schemas_response.json")
sample_list_schemas_response = {200: raw_list_schemas_response}


class ListSchemasResponse(BaseModel):
    """
    The schema for responses from the /schemas endpoint.
    """

    default_schemas: list = Field(
        description="The schemas that ship with with this service by default."
    )
    custom_schemas: list = Field(
        description="Additional schemas that users have uploaded to this service beyond"
        " the ones come by default."
    )


@app.get("/schemas", responses=sample_list_schemas_response)
async def list_schemas() -> ListSchemasResponse:
    """
    Get a list of all the parsing schemas currently available. Default schemas are ones
    that are packaged by default with this service. Custom schemas are any additional
    schema that users have chosen to upload to this service (this feature is not yet
    implemented)
    """
    default_schemas = os.listdir(Path(__file__).parent / "default_schemas")
    custom_schemas = os.listdir(Path(__file__).parent / "custom_schemas")
    custom_schemas = [schema for schema in custom_schemas if schema != ".keep"]
    schemas = {"default_schemas": default_schemas, "custom_schemas": custom_schemas}
    return schemas


class GetSchemaResponse(BaseModel):
    """
    The schema for responses from the /schemas endpoint when a specific schema is
    queried.
    """

    message: str = Field(
        description="A message describing the result of a request to "
        "the /parse_message endpoint."
    )
    parsing_schema: dict = Field(
        description="A set of key:value pairs containing the values extracted from the "
        "message."
    )


# /schemas/{parsing_schema_name} endpoint #
raw_get_schema_response = read_json_from_assets("sample_get_schema_response.json")
sample_get_schema_response = {200: raw_get_schema_response}


@app.get(
    "/schemas/{parsing_schema_name}",
    status_code=200,
    responses=sample_get_schema_response,
)
async def get_schema(parsing_schema_name: str, response: Response) -> GetSchemaResponse:
    """
    Get the schema specified by 'parsing_schema_name'.
    """
    try:
        parsing_schema = load_parsing_schema(parsing_schema_name)
    except FileNotFoundError as error:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": error.__str__(), "parsing_schema": {}}
    return {"message": "Schema found!", "parsing_schema": parsing_schema}


PARSING_SCHEMA_DATA_TYPES = Literal[
    "string", "integer", "float", "boolean", "date", "datetime", "array"
]


class ParsingSchemaSecondaryFieldModel(BaseModel):
    fhir_path: str
    data_type: PARSING_SCHEMA_DATA_TYPES
    nullable: bool


class ParsingSchemaFieldModel(BaseModel):
    fhir_path: str
    data_type: PARSING_SCHEMA_DATA_TYPES
    nullable: bool
    secondary_schema: Optional[Dict[str, ParsingSchemaSecondaryFieldModel]]


class ParsingSchemaModel(BaseModel):
    parsing_schema: Dict[str, ParsingSchemaFieldModel] = Field(
        description="A JSON formatted parsing schema to upload."
    )
    overwrite: Optional[bool] = Field(
        description="When `true` if a schema already exists for the provided name it "
        "will be replaced. When `false` no action will be taken and the response will "
        "indicate that a schema for the given name already exists. To proceed submit a "
        "new request with a different schema name or set this field to `true`.",
        default=False,
    )


class PutSchemaResponse(BaseModel):
    """
    The schema for responses from the /schemas endpoint when a schema is uploaded.
    """

    message: str = Field(
        "A message describing the result of a request to " "upload a parsing schema."
    )


upload_schema_request_examples = read_json_from_assets(
    "sample_upload_schema_requests.json"
)

upload_schema_response_examples = {
    200: "sample_upload_schema_response.json",
    201: "sample_update_schema_response.json",
    400: "sample_upload_schema_failure_response.json",
}
for status_code, file_name in upload_schema_response_examples.items():
    upload_schema_response_examples[status_code] = read_json_from_assets(file_name)
    upload_schema_response_examples[status_code]["model"] = PutSchemaResponse


@app.put(
    "/schemas/{parsing_schema_name}",
    status_code=200,
    response_model=PutSchemaResponse,
    responses=upload_schema_response_examples,
)
async def upload_schema(
    parsing_schema_name: str,
    input: Annotated[ParsingSchemaModel, Body(examples=upload_schema_request_examples)],
    response: Response,
) -> PutSchemaResponse:
    """
    Upload a new parsing schema to the service or update an existing schema.
    """

    file_path = Path(__file__).parent / "custom_schemas" / parsing_schema_name
    schema_exists = file_path.exists()
    if schema_exists and not input.overwrite:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {
            "message": f"A schema for the name '{parsing_schema_name}' already exists. "
            "To proceed submit a new request with a different schema name or set the "
            "'overwrite' field to 'true'."
        }

    # Convert Pydantic models to dicts so they can be serialized to JSON.
    for field in input.parsing_schema:
        field_dict = input.parsing_schema[field].dict()
        if "secondary_schema" in field_dict and field_dict["secondary_schema"] is None:
            del field_dict["secondary_schema"]
        input.parsing_schema[field] = field_dict

    with open(file_path, "w") as file:
        json.dump(input.parsing_schema, file, indent=4)

    if schema_exists:
        return {"message": "Schema updated successfully!"}
    else:
        response.status_code = status.HTTP_201_CREATED
        return {"message": "Schema uploaded successfully!"}
