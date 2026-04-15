from datetime import UTC, datetime
from pathlib import Path

from app.repositories.interfaces.vector_store_repository import IVectorStoreRepository
from app.services.interfaces.vector_store_admin_service import IVectorStoreAdminService


class VectorStoreAdminService(IVectorStoreAdminService):
    def __init__(
        self,
        vector_store_repository: IVectorStoreRepository,
        backup_root_dir: Path,
    ) -> None:
        self._vector_store_repository = vector_store_repository
        self._backup_root_dir = backup_root_dir
        self._backup_root_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> dict:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_name = f"backup_{timestamp}"
        backup_dir = self._backup_root_dir / backup_name

        result = self._vector_store_repository.backup(backup_dir)
        result["backup_name"] = backup_name
        result["backup_dir"] = str(backup_dir)
        return result

    def restore_latest(self) -> dict:
        candidates = [path for path in self._backup_root_dir.iterdir() if path.is_dir()]
        if not candidates:
            return {
                "restored": False,
                "reason": "No backup found",
            }

        latest = max(candidates, key=lambda path: path.name)
        result = self._vector_store_repository.restore(latest)
        result["backup_name"] = latest.name
        result["backup_dir"] = str(latest)
        return result

    def status(self) -> dict:
        return {
            "document_count": self._vector_store_repository.document_count(),
            "backup_root_dir": str(self._backup_root_dir),
        }

    def clear(self) -> dict:
        return self._vector_store_repository.clear()
