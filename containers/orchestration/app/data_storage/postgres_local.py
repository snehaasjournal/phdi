from app.data_storage.fhir_storage import FHIRStorage
from app.data_storage.dal import DataAccessLayer
from sqlalchemy import URL
import os


class PostgresLocalFhirStorage(FHIRStorage):
    def __init__(self) -> None:
        # This is where the definition for the connection URL will need to go
        database = os.environ.get("POSTGRES_DB")
        user = os.environ.get("POSTGRES_USER")
        password = os.environ.get("POSTGRES_PASSWORD")
        host = os.environ.get("DATABASE_CONNECTION")
        port = os.environ.get("DATABASE_PORT")
        database_url = URL.create(
            "postgresql+pg8000",
            username=user,
            password=password,  # plain (unescaped) text
            host=host,
            port=port,
            database=database,
        )
        print(database_url)
        self.dal = DataAccessLayer()
        self.dal.get_connection(database_url)

    def store_bundle(self):
        pass

    def retrieve_bundle(self, id):
        pass
