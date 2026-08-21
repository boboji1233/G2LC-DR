"""Verified dataset identity, modality, lock, and source-family registry."""

from __future__ import annotations

from g2lc.data.adapters.base import AdapterSpec, MetadataAdapter
from g2lc.errors import SourceValidationError
from g2lc.types import Modality

SPECS = {
    "messidor1": AdapterSpec(
        dataset_id="messidor1",
        source_family="MESSIDOR1",
        default_modality=Modality.CFP,
        license_id="messidor1",
        warnings=(
            "Use original MESSIDOR-1, never MESSIDOR-2, for MAPLES correspondence.",
            "All MAPLES-corresponding cases are locked same-case final tests.",
        ),
        maples_test_locked=True,
        license_confirmation_required=True,
    ),
    "maples_dr": AdapterSpec(
        dataset_id="maples_dr",
        source_family="MESSIDOR1",
        default_modality=Modality.CFP,
        license_id="maples_dr",
        warnings=("MAPLES-DR and MESSIDOR-1 are the same underlying image family.",),
        maples_test_locked=True,
    ),
    "ddr": AdapterSpec(
        dataset_id="ddr",
        source_family="OIA_DDR",
        default_modality=Modality.CFP,
        license_id="ddr",
        warnings=("MMRDR-CFP is derived from OIA-DDR and is not an independent domain.",),
    ),
    "mmrdr_cfp": AdapterSpec(
        dataset_id="mmrdr_cfp",
        source_family="OIA_DDR",
        default_modality=Modality.CFP,
        license_id="mmrdr",
        warnings=(
            "Treat DDR and MMRDR-CFP as one source family and run cross-copy deduplication.",
        ),
    ),
    "mmrdr_uwf": AdapterSpec(
        dataset_id="mmrdr_uwf",
        source_family="MMRDR_UWF",
        default_modality=Modality.UWF,
        license_id="mmrdr",
    ),
    "idrid": AdapterSpec(
        dataset_id="idrid",
        source_family="IDRID",
        default_modality=Modality.CFP,
        license_id="idrid",
        required_path_groups=(
            ("A_Segmentation",),
            ("B_Disease_Grading",),
            ("C_Localization",),
        ),
        warnings=("Use official splits; an unlabelled task/image remains UNKNOWN.",),
        license_confirmation_required=True,
    ),
    "deepdrid": AdapterSpec(
        dataset_id="deepdrid",
        source_family="DEEPDRID",
        default_modality=Modality.CFP,
        license_id="deepdrid",
        required_path_groups=(("regular_fundus_images", "ultra-widefield_images"),),
        warnings=("All views from the same patient/eye must remain in one split.",),
    ),
    "fgadr": AdapterSpec(
        dataset_id="fgadr",
        source_family="FGADR",
        default_modality=Modality.CFP,
        license_id="fgadr",
        warnings=(
            "Research-use agreement data and personal download links must not be redistributed.",
        ),
        license_confirmation_required=True,
    ),
    "retinal_lesions": AdapterSpec(
        dataset_id="retinal_lesions",
        source_family="EYEPACS_RLDR",
        default_modality=Modality.CFP,
        license_id="retinal_lesions",
        warnings=("Audit against EyePACS because Retinal-Lesions is an EyePACS subset.",),
        license_confirmation_required=True,
    ),
    "tjdr": AdapterSpec(
        dataset_id="tjdr",
        source_family="TJDR",
        default_modality=Modality.CFP,
        license_id="tjdr",
        warnings=("Only source-file structure is inventoried; filenames never supply diagnoses.",),
    ),
}

ALIASES = {"maples_messidor": "maples_dr"}


def adapter_for(dataset_id: str) -> MetadataAdapter:
    """Return a metadata adapter or an actionable supported-ID error."""

    try:
        return MetadataAdapter(SPECS[ALIASES.get(dataset_id, dataset_id)])
    except KeyError as exc:
        raise SourceValidationError(
            f"unsupported adapter {dataset_id!r}; choose one of {sorted(SPECS)}"
        ) from exc
