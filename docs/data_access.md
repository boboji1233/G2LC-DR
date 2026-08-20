# Data Access and License Boundaries

This page summarizes the official acquisition actions from research-plan §6. Source
terms can change and must be rechecked on the acquisition date. The repository never
auto-downloads gated data or redistributes medical images.

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

Every local adapter will require a user-supplied path and will create metadata only.
The planned license registry records acquisition date, license version, redistribution
status, checksums and approval state. An absent dataset is a blocker, not permission to
fabricate labels or results.

