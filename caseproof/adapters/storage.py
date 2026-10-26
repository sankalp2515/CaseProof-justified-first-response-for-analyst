from caseproof.adapters.gcs_storage import GCSStorage
from caseproof.adapters.local_storage import LocalStorage


def build_storage(settings):
    if settings.storage_backend == "local":
        return LocalStorage(settings.object_dir)
    if settings.storage_backend == "gcs":
        if not settings.gcs_bucket:
            raise ValueError("GCS_BUCKET is required for cloud evidence storage")
        return GCSStorage(settings.gcs_bucket)
    raise ValueError("Unsupported storage_backend")
