from contextlib import contextmanager
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session


class DataAccessLayer(object):
    """
    Base class for Database API objects - manages transactions and sessions.
    This DAL is specific to the FHIR storage database.
    """

    def __init__(self) -> None:
        self.engine = None
        self.Meta = MetaData()

    def get_connection(self, engine_url):
        self.engine = create_engine(engine_url)

    @contextmanager
    def transaction(self) -> None:
        """
        Executes a database transaction.
        This method wraps a session object in transactional scope
        used for basic CRUD applications.

        :return: SQLAlchemy session object
        :raises ValueError: if an error occurs during the transaction
        """
        session = self.get_session()

        try:
            yield session
            session.commit()

        except Exception as error:
            session.rollback()
            raise ValueError(f"{error}")

        finally:
            session.close()

    def get_session(self) -> scoped_session:
        """
        Get a session object

        this method returns a session object to the caller

        :return: SQLAlchemy scoped session
        """

        session = scoped_session(
            sessionmaker(bind=self.engine)
        )  # NOTE extra config can be implemented in this call to sessionmaker factory
        return session()
