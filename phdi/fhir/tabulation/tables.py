import fhirpathpy
import json
import random
import pathlib

from functools import cache
from typing import Any, Callable, Literal, List, Union

from phdi.cloud.core import BaseCredentialManager
from phdi.fhir import fhir_server_get
from phdi.tabulation.tables import load_schema, write_table


def apply_selection_criteria(
    value: List[Any],
    selection_criteria: Literal["first", "last", "random", "all"],
) -> Union[str, List[str]]:
    """
    Given a list of values parsed from a FHIR resource, return value(s) according to the
    selection criteria. In general a single value is returned, but when
    selection_criteria is set to "all" a list containing all of the parsed values is
    returned.

    :param value: A list containing the values parsed from a FHIR resource.
    :param selection_criteria: A string indicating which element(s) of a list to select.
    """

    if selection_criteria == "first":
        value = value[0]
    elif selection_criteria == "last":
        value = value[-1]
    elif selection_criteria == "random":
        value = random.choice(value)

    # Temporary hack to ensure no structured data is written using pyarrow.
    # Currently Pyarrow does not support mixing non-structured and structured data.
    # https://github.com/awslabs/aws-data-wrangler/issues/463
    # Will need to consider other methods of writing to parquet if this is an essential
    # feature.
    if type(value) == dict:
        value = json.dumps(value)
    elif type(value) == list:
        value = ",".join(value)
    return value


def apply_schema_to_resource(resource: dict, schema: dict) -> dict:
    """
    Creates and returns a dictionary of data based on a FHIR resource and a schema. The
    keys of the created dict are the "new names" for the fields in the given schema, and
    the values are the elements of the given resource that correspond to these fields.
    Here, "new name" is a property contained in the schema that specifies what a
    particular variable should be called. If a schema can't be found for the given
    resource type, the raw resource is instead returned.

    :param resource: A FHIR resource on which to apply a schema.
    :param schema: A schema specifying the desired values by FHIR resource type.
    """

    data = {}
    resource_schema = schema.get(resource.get("resourceType", ""))
    if resource_schema is None:
        return data
    for field in resource_schema.keys():
        path = resource_schema[field]["fhir_path"]

        parse_function = _get_fhirpathpy_parser(path)
        value = parse_function(resource)

        if len(value) == 0:
            data[resource_schema[field]["new_name"]] = ""
        else:
            selection_criteria = resource_schema[field]["selection_criteria"]
            value = apply_selection_criteria(value, selection_criteria)
            data[resource_schema[field]["new_name"]] = str(value)

    return data


def generate_table(
    schema: dict,
    output_path: pathlib.Path,
    output_format: Literal["parquet"],
    fhir_url: str,
    cred_manager: BaseCredentialManager,
):
    """
    Given the schema for a single table, make the table.

    :param schema: A schema specifying the desired values by FHIR resource type.
    :param output_path: A path specifying where the table should be written.
    :param output_format: A string indicating the file format to be used.
    :param fhir_url: URL to a FHIR server.
    :param cred_manager: Service used to get an access token used to make a
        request.
    """
    output_path.mkdir(parents=True, exist_ok=True)
    for resource_type in schema:

        output_file_name = output_path / f"{resource_type}.{output_format}"

        # TODO: make _count (and other query parameters) configurable
        query = f"/{resource_type}?_count=1000"
        url = fhir_url + query

        writer = None
        next_page = True
        while next_page:
            response = fhir_server_get(url, cred_manager)
            if response.status_code != 200:
                break

            # Load queried data.
            query_result = json.loads(response.content)
            data = []

            # Extract values specified by schema from each resource.
            # values_from_resource is a dictionary of the form:
            # {field1:value1, field2:value2, ...}.

            for resource in query_result["entry"]:
                values_from_resource = apply_schema_to_resource(
                    resource["resource"], schema
                )
                if values_from_resource != {}:
                    data.append(values_from_resource)

            # Write data to file.
            writer = write_table(data, output_file_name, output_format, writer)

            # Check for an additional page of query results.
            for link in query_result.get("link"):
                if link.get("relation") == "next":
                    url = link.get("url")
                    break
                else:
                    next_page = False

        if writer is not None:
            writer.close()


def generate_all_tables_in_schema(
    schema_path: pathlib.Path,
    base_output_path: pathlib.Path,
    output_format: Literal["parquet"],
    fhir_url: str,
    cred_manager: BaseCredentialManager,
):
    """
    Given the url for a FHIR server, the location of a schema file, and and output
    directory generate the specified schema and store the tables in the desired
    location.

    :param schema_path: A path to the location of a YAML schema config file.
    :param base_output_path: A path to the directory where tables of the schema should
        be written.
    :param output_format: Specifies the file format of the tables to be generated.
    :param fhir_url: URL to a FHIR server.
    :param cred_manager: Service used to get an access token used to make a
        request.
    """

    schema = load_schema(schema_path)

    for table in schema.keys():
        output_path = base_output_path / table
        generate_table(
            schema[table], output_path, output_format, fhir_url, cred_manager
        )


@cache
def _get_fhirpathpy_parser(fhirpath_expression: str) -> Callable:
    """
    Return a fhirpathpy parser for a specific FHIRPath.  This cached function minimizes
    calls to the relatively expensive :func:`fhirpathpy.compile` function for any given
    `fhirpath_expression`

    :param fhirpath_expression: The FHIRPath expression to evaluate
    """
    return fhirpathpy.compile(fhirpath_expression)
