from phdi.containers.base_service import BaseService
from pathlib import Path
import requests
import uuid
import json
from pydantic import BaseModel
from typing import Optional, Literal
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

USE_CASES = Literal["social-determinants", "newborn-screening", "syphilis", "cancer"]

FHIR_SERVERS = {
    "meld": {"hostname": "https://gw.interop.community/HeliosConnectathonSa/open"},
    "ehealthexchange": {
        "hostname": "https://concept01.ehealthexchange.org:52780/fhirproxy/r4/",
        "username": "svc_eHxFHIRSandbox",
        "password": "willfulStrongStandurd7",
        "headers": {
            "Accept": "application/json, application/*+json, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/fhir+json; charset=UTF-8",
            "X-DESTINATION": "CernerHelios",
            "X-POU": "TREAT",
            "X-Request-Id": str(uuid.uuid4()),
            "prefer": "return=representation",
            "Cache-Control": "no-cache",
            "OAUTHSCOPES": "system/Condition.read system/Encounter.read system/Immunization.read system/MedicationRequest.read system/Observation.read system/Patient.read system/Procedure.read system/MedicationAdministration.read system/DiagnosticReport.read system/RelatedPerson.read",
        },
    },
}


# Instantiate FastAPI via PHDI's BaseService class
app = BaseService(
    service_name="DIBBS FHIR Connector",
    description_path=Path(__file__).parent.parent / "description.md",
).start()


class UseCaseQueryRequest(BaseModel):
    fhir_server: Literal["meld", "ehealthexchange"]
    first_name: str
    last_name: str
    dob: str
    mrn: Optional[str]
    phone: Optional[str]
    street: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip: Optional[str]


@app.post("/use-case-query/{use_case}")
async def use_case_query(use_case: USE_CASES, input: UseCaseQueryRequest):
    # Connect to FHIR Server
    fhir_host = FHIR_SERVERS[input.fhir_server]["hostname"]
    session = requests.Session()
    fhir_server_config = FHIR_SERVERS[input.fhir_server]
    if fhir_server_config.get("username") and fhir_server_config.get("password"):
        session.auth = (
            fhir_server_config["username"],
            fhir_server_config["password"],
        )
    if fhir_server_config.get("headers"):
        session.headers = fhir_server_config["headers"]
    session.verify = False

    # Find Patient

    patient_query = f"{fhir_host}/Patient?given={input.first_name}&family={input.last_name}&birthdate={input.dob}"
    response = session.get(patient_query)

    if response.status_code != 200:
        return {
            "error": "Patient search failed.",
            "status_code": response.status_code,
            "query": patient_query,
            "fhir_server_response": response.text,
        }

    patient_searchset = response.json()

    if patient_searchset["total"] > 1:
        return {"error": "Multiple patients found. Please refine your search."}
    elif patient_searchset["total"] == 0:
        return {"error": "No patients found. Please refine your search."}

    patient_id = patient_searchset["entry"][0]["resource"]["id"]

    # Use Case Query
    if use_case == "social-determinants":
        use_case_query = (
            f"{fhir_host}/Observation?subject=Patient/{patient_id}&category=survey"
        )
        use_case_response = session.get(use_case_query).json()

    elif use_case == "newborn-screening":
        use_case_query = (
            f"{fhir_host}/Observation?subject=Patient/{patient_id}&category=laboratory"
        )
        screening_loinc_codes = [
            "73700-7",
            "73698-3",
            "54108-6",
            "54109-4",
            "58232-0",
            "57700-7",
            "73739-5",
            "73742-9",
            "2708-6",
            "8336-0",
        ]
        loinc_fitler = "http://loinc.org|" + ",".join(screening_loinc_codes)
        use_case_query = f"{use_case_query}&code={loinc_fitler}"
        use_case_response = session.get(use_case_query).json()

    elif use_case == "syphilis":
        syphilis_loincs = ["LP70657-9", "98212-4"]
        syphilis_loincs = ",".join(syphilis_loincs)
        conditon_query = f"{fhir_host}/Condition?subject={patient_id}&code=76272004"
        observation_query = (
            f"{fhir_host}/Observation?subject={patient_id}&code={syphilis_loincs}"
        )
        diagnositic_report_query = (
            f"{fhir_host}/DiagnosticReport?subject={patient_id}&code={syphilis_loincs}"
        )
        encounter_query = f"{fhir_host}/Encounter?subject={patient_id}&reason-reference=Condition/105H"

        queries = [
            conditon_query,
            observation_query,
            diagnositic_report_query,
            encounter_query,
        ]
        use_case_response = concatenate_queries(queries, session)

    elif use_case == "cancer":
        cancer_snomeds = ["92814006"]
        cancer_snomeds = ",".join(cancer_snomeds)
        cancer_encounter_codes = ["15301000"]
        cancer_encounter_codes = ",".join(cancer_encounter_codes)
        cancer_medications = ["828265"]
        cancer_medications = ",".join(cancer_medications)

        conditon_query = (
            f"{fhir_host}/Condition?subject={patient_id}&code={cancer_snomeds}"
        )
        encounter_query = (
            f"{fhir_host}/Encounter?subject={patient_id}&type={cancer_encounter_codes}"
        )
        medication_request_query = f"{fhir_host}/MedicationRequest?subject={patient_id}&code={cancer_medications}"
        medication_query = f"{fhir_host}/Medication?code={cancer_medications}"
        # medication_administration_query = f"{fhir_host}/MedicationAdministration?subject={patient_id}&code={cancer_medications}"

        queries = [
            conditon_query,
            encounter_query,
            medication_request_query,
            medication_query,
            # medication_administration_query,
        ]
        use_case_response = concatenate_queries(queries, session)

    return use_case_response


def concatenate_queries(queries, session):
    use_case_response = None
    for query in queries:
        print(query)
        partial_response = session.get(query)
        if use_case_response is None:
            use_case_response = partial_response.json()
        else:
            use_case_response["entry"].extend(partial_response.json()["entry"])
        use_case_response["total"] = len(use_case_response["entry"])
    return use_case_response

 # Serve Static Files
app.mount("/front-end", StaticFiles(directory="./app/front-end"), name="front-end")

# Root endpoint to serve the HTML page
@app.get("/front-end")
async def root():
    return FileResponse('./app/front-end/index.html')
