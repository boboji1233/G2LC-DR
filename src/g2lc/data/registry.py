"""Versioned dataset access/licence ledger with no acquisition side effects."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import Field, ValidationError, field_validator

from g2lc.data.adapters import AdapterInspection, AdapterState, adapter_for
from g2lc.errors import SourceValidationError
from g2lc.types import StrictModel
from g2lc.utils.io import load_yaml, validation_error


class AccessMode(StrEnum):
    """How the official source says data access is initiated."""

    PUBLIC = "PUBLIC"
    REGISTRATION = "REGISTRATION"
    REQUEST = "REQUEST"


class ApplicationStatus(StrEnum):
    """Repository-safe status; no private correspondence is stored."""

    NOT_REQUESTED = "NOT_REQUESTED"
    NOT_DOWNLOADED = "NOT_DOWNLOADED"
    REQUESTED = "REQUESTED"
    APPROVED_NOT_DOWNLOADED = "APPROVED_NOT_DOWNLOADED"
    AVAILABLE_LOCAL = "AVAILABLE_LOCAL"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


class PatientIdAvailability(StrEnum):
    """Whether a verified official layout is expected to carry grouping identity."""

    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNKNOWN = "UNKNOWN"
    EXPECTED_UNVERIFIED = "EXPECTED_UNVERIFIED"


class DatasetRegistryEntry(StrictModel):
    """Public, versioned facts and owner actions for one adapter."""

    dataset_id: str = Field(min_length=1)
    official_name: str = Field(min_length=1)
    official_landing_page: str = Field(min_length=1)
    official_publication: str | None = None
    access_mode: AccessMode
    application_status: ApplicationStatus
    license_access_class: str = Field(min_length=1)
    redistribution_restrictions: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    patient_id_availability: PatientIdAvailability
    expected_local_layout: list[str] = Field(min_length=1)
    last_checked_date: date
    next_owner_action: str = Field(min_length=1)

    @field_validator("official_landing_page", "official_publication")
    @classmethod
    def official_urls_are_http(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://", "doi:")):
            raise ValueError("official source references must be HTTP(S) URLs or DOI references")
        return value


class DatasetRegistry(StrictModel):
    """Canonical Stage-2A access ledger."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    datasets: list[DatasetRegistryEntry] = Field(min_length=1)

    @field_validator("datasets")
    @classmethod
    def dataset_ids_are_unique(
        cls, values: list[DatasetRegistryEntry]
    ) -> list[DatasetRegistryEntry]:
        ids = [item.dataset_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset registry IDs must be unique")
        return values

    def entry(self, dataset_id: str) -> DatasetRegistryEntry:
        """Return one record or an actionable error."""

        for item in self.datasets:
            if item.dataset_id == dataset_id:
                return item
        raise SourceValidationError(
            f"dataset {dataset_id!r} is not registered; choose one of "
            f"{sorted(item.dataset_id for item in self.datasets)}"
        )


class DatasetStatus(StrictModel):
    """One registry record joined to its truthful local adapter state."""

    dataset_id: str
    official_name: str
    source_family: str
    application_status: ApplicationStatus
    adapter_state: AdapterState
    local_path: str
    image_count: int
    next_owner_action: str
    errors: list[str]


def load_dataset_registry(path: str | Path = "data/dataset_registry.yaml") -> DatasetRegistry:
    """Load the public access ledger and ensure every entry has an adapter."""

    source = Path(path)
    try:
        registry = DatasetRegistry.model_validate(load_yaml(source))
    except ValidationError as exc:
        raise validation_error(source, exc) from exc
    for item in registry.datasets:
        adapter = adapter_for(item.dataset_id)
        if adapter.spec.source_family != item.source_family:
            raise SourceValidationError(
                "registry source_family differs from adapter policy", path=source
            )
    return registry


def inspect_registry_status(
    registry: DatasetRegistry,
    roots: dict[str, str] | None = None,
    *,
    license_confirmed: set[str] | None = None,
) -> list[DatasetStatus]:
    """Inspect explicit/default local roots without downloading or accepting terms."""

    roots = roots or {}
    confirmations = license_confirmed or set()
    statuses: list[DatasetStatus] = []
    for entry in registry.datasets:
        root = Path(roots.get(entry.dataset_id, f"data/raw/{entry.dataset_id}"))
        confirmed = entry.dataset_id in confirmations or entry.application_status in {
            ApplicationStatus.APPROVED_NOT_DOWNLOADED,
            ApplicationStatus.AVAILABLE_LOCAL,
        }
        inspection = adapter_for(entry.dataset_id).inspect_root(root, license_confirmed=confirmed)
        if (
            inspection.state is AdapterState.MISSING_FILES
            and entry.access_mode in {AccessMode.REQUEST, AccessMode.REGISTRATION}
            and entry.application_status is ApplicationStatus.NOT_REQUESTED
        ):
            inspection = AdapterInspection(
                dataset_id=inspection.dataset_id,
                source_family=inspection.source_family,
                state=AdapterState.LICENSE_REQUIRED,
                local_path=inspection.local_path,
                image_count=inspection.image_count,
                missing_paths=inspection.missing_paths,
                errors=["official access action has not been completed"],
                source_version=inspection.source_version,
                warnings=inspection.warnings,
            )
        statuses.append(
            DatasetStatus(
                dataset_id=entry.dataset_id,
                official_name=entry.official_name,
                source_family=entry.source_family,
                application_status=entry.application_status,
                adapter_state=inspection.state,
                local_path=inspection.local_path,
                image_count=inspection.image_count,
                next_owner_action=entry.next_owner_action,
                errors=inspection.errors,
            )
        )
    return statuses


def access_plan(registry: DatasetRegistry) -> list[dict[str, str]]:
    """Return owner actions without private contact details or inferred completion."""

    return [
        {
            "dataset_id": item.dataset_id,
            "state": item.application_status.value,
            "access_mode": item.access_mode.value,
            "official_landing_page": item.official_landing_page,
            "next_owner_action": item.next_owner_action,
        }
        for item in sorted(registry.datasets, key=lambda entry: entry.dataset_id)
    ]
