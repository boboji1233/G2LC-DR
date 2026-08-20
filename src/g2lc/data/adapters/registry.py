"""Verified dataset identity, modality, lock, and source-family registry."""

from __future__ import annotations

from g2lc.data.adapters.base import AdapterSpec, MetadataAdapter
from g2lc.errors import SourceValidationError
from g2lc.types import Modality

SPECS = {
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
    ),
    "maples_messidor": AdapterSpec(
        dataset_id="maples_messidor",
        source_family="MESSIDOR1",
        default_modality=Modality.CFP,
        license_id="maples_dr",
        warnings=(
            "All 198 MAPLES/MESSIDOR cases are locked final test data.",
            "MESSIDOR-2 cannot substitute for original MESSIDOR-1 images.",
        ),
        maples_test_locked=True,
    ),
    "retinal_lesions": AdapterSpec(
        dataset_id="retinal_lesions",
        source_family="EYEPACS_RLDR",
        default_modality=Modality.CFP,
        license_id="retinal_lesions",
        warnings=("Audit against EyePACS because Retinal-Lesions is an EyePACS subset.",),
    ),
}


def adapter_for(dataset_id: str) -> MetadataAdapter:
    """Return a metadata adapter or an actionable supported-ID error."""

    try:
        return MetadataAdapter(SPECS[dataset_id])
    except KeyError as exc:
        raise SourceValidationError(
            f"unsupported adapter {dataset_id!r}; choose one of {sorted(SPECS)}"
        ) from exc
