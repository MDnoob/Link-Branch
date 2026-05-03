"""
storage.py — Dual-mode asset storage helper

If OCI_BUCKET_NAME (and friends) are set in .env, all uploads go to
Oracle Cloud Object Storage.  Otherwise files are saved to
static/uploads/ on local disk — no code changes needed to switch.

Public API
----------
    save_asset(contents: bytes, filename: str) -> str
        Persist the bytes and return a publicly accessible URL.

    delete_asset(filename: str, url: str) -> None
        Remove the file from wherever it was stored.

    using_oci() -> bool
        True when OCI credentials are fully configured.
"""

import io
import os

UPLOAD_DIR = "static/uploads"

# ---------------------------------------------------------------------------
# Detect whether OCI is configured
# ---------------------------------------------------------------------------

def using_oci() -> bool:
    """Return True only when all required OCI env vars are present."""
    required = [
        "OCI_USER_OCID",
        "OCI_TENANCY_OCID",
        "OCI_FINGERPRINT",
        "OCI_REGION",
        "OCI_NAMESPACE",
        "OCI_BUCKET_NAME",
        "OCI_PRIVATE_KEY_PATH",
    ]
    return all(os.getenv(k, "").strip() for k in required)


# ---------------------------------------------------------------------------
# OCI helpers (only imported when OCI is configured)
# ---------------------------------------------------------------------------

def _oci_client():
    """Build and return an OCI ObjectStorageClient from env vars."""
    import oci  # lazy import — not installed in all environments
    config = {
        "user":        os.getenv("OCI_USER_OCID"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "tenancy":     os.getenv("OCI_TENANCY_OCID"),
        "region":      os.getenv("OCI_REGION"),
        "key_file":    os.getenv("OCI_PRIVATE_KEY_PATH"),
    }
    return oci.object_storage.ObjectStorageClient(config)


def _oci_public_url(filename: str) -> str:
    """
    Build the public HTTPS URL for an object in the bucket.
    Oracle public-bucket URL pattern:
      https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<filename>
    """
    region    = os.getenv("OCI_REGION")
    namespace = os.getenv("OCI_NAMESPACE")
    bucket    = os.getenv("OCI_BUCKET_NAME")
    return (
        f"https://objectstorage.{region}.oraclecloud.com"
        f"/n/{namespace}/b/{bucket}/o/{filename}"
    )


def _oci_save(contents: bytes, filename: str) -> str:
    """Upload bytes to OCI and return the public URL."""
    client    = _oci_client()
    namespace = os.getenv("OCI_NAMESPACE")
    bucket    = os.getenv("OCI_BUCKET_NAME")
    client.put_object(
        namespace_name=namespace,
        bucket_name=bucket,
        object_name=filename,
        put_object_body=io.BytesIO(contents),
    )
    return _oci_public_url(filename)


def _oci_delete(filename: str) -> None:
    """Delete an object from OCI. Silently ignores 404 (already gone)."""
    try:
        import oci
        client    = _oci_client()
        namespace = os.getenv("OCI_NAMESPACE")
        bucket    = os.getenv("OCI_BUCKET_NAME")
        client.delete_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=filename,
        )
    except Exception:
        pass  # object already deleted or never existed — safe to ignore


# ---------------------------------------------------------------------------
# Local-disk helpers
# ---------------------------------------------------------------------------

def _local_save(contents: bytes, filename: str) -> str:
    """Write bytes to static/uploads/ and return the relative URL."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(UPLOAD_DIR, filename)
    with open(save_path, "wb") as f:
        f.write(contents)
    return f"/static/uploads/{filename}"


def _local_delete(filename: str) -> None:
    """Remove a file from static/uploads/. Silently ignores missing files."""
    disk_path = os.path.join(UPLOAD_DIR, filename)
    try:
        os.remove(disk_path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_asset(contents: bytes, filename: str) -> str:
    """
    Persist asset bytes and return a publicly accessible URL.

    Routing:
      - OCI credentials present  → Oracle Cloud Object Storage
      - Otherwise                → local disk (static/uploads/)
    """
    if using_oci():
        return _oci_save(contents, filename)
    return _local_save(contents, filename)


def delete_asset(filename: str, url: str = "") -> None:
    """
    Delete an asset from wherever it is stored.

    `url` is used as a hint: if it starts with http it was an OCI upload,
    so we use OCI delete even if OCI is no longer configured (e.g. during
    a migration).  Filename is always the canonical lookup key.
    """
    if using_oci() or (url or "").startswith("http"):
        _oci_delete(filename)
    else:
        _local_delete(filename)
