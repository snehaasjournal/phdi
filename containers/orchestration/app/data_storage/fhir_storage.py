from abc import ABC, abstractmethod


class FHIRStorage(ABC):
    @abstractmethod
    def store_bundle(self):
        pass

    @abstractmethod
    def retrieve_bundle(self, id):
        pass
