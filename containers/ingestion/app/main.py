from pathlib import Path

from dibbs.base_service import BaseService

from app.config import get_settings
from app.routers import cloud_storage
from app.routers import fhir_geospatial
from app.routers import fhir_harmonization_standardization
from app.routers import fhir_linkage_link
from app.routers import fhir_transport_http

# Read settings immediately to fail fast in case there are invalid values.
get_settings()

# Instantiate FastAPI via DIBBs' BaseService class
app = BaseService(
    service_name="DIBBs Ingestion Service",
    service_path="/ingestion",
    description_path=Path(__file__).parent.parent / "description.md",
).start()

app.include_router(fhir_harmonization_standardization.router)
app.include_router(fhir_geospatial.router)
app.include_router(fhir_linkage_link.router)
app.include_router(fhir_transport_http.router)
app.include_router(cloud_storage.router)
