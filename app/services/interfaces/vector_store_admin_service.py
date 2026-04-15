from abc import ABC, abstractmethod


class IVectorStoreAdminService(ABC):
    @abstractmethod
    def create_backup(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def restore_latest(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> dict:
        raise NotImplementedError
