# Data Access and License Boundaries

This page summarizes the official acquisition actions from research-plan §6. The
machine-readable authority is `data/dataset_registry.yaml`. Source terms can change and
must be rechecked on the acquisition date. The repository never downloads data, accepts
terms, submits forms, or redistributes medical images.

| Dataset | Official entry | Required action | Source-family/lock note |
|---|---|---|---|
| DDR/OIA-DDR | https://github.com/nkicsl/DDR-dataset | Follow official links and verify archive hashes | `OIA_DDR`; overlaps MMRDR-CFP |
| MMRDR | https://figshare.com/articles/dataset/MMRDR/29423747 | Public Figshare metadata/files; verify current license and checksums | CFP is `OIA_DDR`; UWF is separate modality validation |
| IDRiD | https://idrid.grand-challenge.org/Data/ | Register/accept IEEE DataPort terms; keep official splits | Missing task labels remain `UNKNOWN` |
| DeepDRiD | https://github.com/deepdrdoc/DeepDRiD | Follow repository/large-file instructions and license | Keep all views from a patient together |
| FGADR | https://csyizhou.github.io/FGADR/ | Sign the research-use agreement and request access | Never publish agreement, personal mail or images |
| MAPLES-DR labels | https://figshare.com/articles/dataset/24328660 | Download labels/AdditionalData from official version | Entire 198-case set is locked test data |
| MESSIDOR-1 images | https://www.adcis.net/en/third-party/messidor/ | Apply to ADCIS; use original MESSIDOR, not MESSIDOR-2 | Must match exactly 198 MAPLES cases |
| Retinal-Lesions | https://github.com/WeiQijie/retinal-lesions | Use the official request form | `EYEPACS_RLDR`; audit against EyePACS |
| TJDR | https://github.com/NekoPii/TJDR | Verify repository and linked-file terms before an explicit download | `TJDR`; do not infer labels from filenames |

Every adapter requires a user-supplied path and returns one explicit state: `READY`,
`MISSING_FILES`, `LICENSE_REQUIRED`, `UNSUPPORTED_VERSION`, or `SCHEMA_MISMATCH`.
Materialization additionally requires `--license-confirmed`. The public registry records
official landing page/publication, access class, application status, restrictions,
source family, patient-ID availability, expected layout, last check, and next owner
action. An absent dataset is a blocker, not permission to fabricate labels or results.

MMRDR Figshare v2 currently advertises CC BY 4.0 at the dataset level; file-level terms
must still be checked at acquisition. MESSIDOR permits research/education use to direct
recipients but prohibits copying and redistribution. These notes are time-stamped facts,
not legal advice or a substitute for reviewing the current source terms.

