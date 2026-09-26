# CSoNet revision for team review — 27 September 2026

This is a revised manuscript and local experiment artifact, **not an assertion that every reviewer request or submission requirement is complete**. Start with the [critical experiment review](../experiments/drift_only/EXPERIMENT_CRITICAL_REVIEW_VI_2026-09-27.md), then read the manuscript and [review response matrix](REVIEW_RESPONSE_MATRIX_VI.md). See [citation audit](CITATION_AUDIT_2026-09-27.md) for source checks and unresolved citation-trigger context.

## Changes

- Kept the accepted title and author block; condensed architecture into responsibilities, one logical diagram, and a monitoring/review contract.
- Replaced the old challenger-recovery evidence in the manuscript with the frozen 120-window study; the previous manuscript/results remain in repository history.
- Added source/split accounting, stable controls, fixed model, family composition scenarios, threshold/window-size sensitivity, and explicit post-hoc mixture interpretation.
- Distinguished standalone KS/BH results from the deployed Evidently preset and from the earlier bounded Locust replay.
- Corrected bibliographic author errors, pinned preprint versions, removed unsupported product-gap claims, and added BH citation.
- Embedded the result and threshold-sensitivity tables directly in the manuscript from the unchanged CSVs. The checked standalone build has 8 pages and no unresolved references or LaTeX box warnings.

## Build the paper

The manuscript has no external table or figure inputs. In the existing Overleaf project, replace the manuscript `.tex` file. The project must already have the official `llncs.cls` and standard packages. The local check copied only this `.tex` file and the class file into a clean directory.

From the repository/extracted bundle root, PowerShell:

```powershell
./graduate/paper/revision/build_paper.ps1
```

The script writes to `graduate/paper/revision/build/`. For other systems, change to `graduate/paper`, ensure `llncs.cls` is discoverable, and run `pdflatex -interaction=nonstopmode -halt-on-error A_Drift-Aware_MLOps_Framework_for_Multi-Model_Serving_CSONET.tex` twice. Bibliography is inline; no BibTeX step is needed.

Optional asset regeneration, from the root:

```powershell
python graduate/paper/revision/build_result_assets.py
```

Assets are already included; regenerating figures is not required to compile. Required Python libraries/versions are in the experiment requirements. This only reformats existing results and does not rerun the study.

## Reproduce the experiment

See [experiment README](../experiments/drift_only/README.md). The review ZIP includes code, saved model, result/row manifests and diagnostics; it **does not include the dataset CSVs**. The team must provide a versioned, authorized acquisition procedure and the matching `data/reference_data.csv` with SHA-256:

```text
0728925d293f433a3f7bce4509c00e1648906c59c59d8e63663e1622a226ef6c
```

Do not assume any current Kaggle download is byte-identical. For a fresh reproduction, placing this exact CSV at `data/reference_data.csv` is sufficient for the runner (other local data CSVs are audited only if present). Use a new output directory; the runner refuses to overwrite the frozen run. Its verifier can validate that new run.

To execute the verifier specifically against archived `results/run_20260926`, supply **all** original data CSVs listed in its `source_file_audit.json`, because that verifier checks every recorded input checksum. This additional requirement is separate from reproducing the core experiment from the reference CSV alone. The whole-pool diagnostics are post-hoc and not independent confirmation.

The runner records `git rev-parse HEAD`. When reproducing from the ZIP outside a Git checkout, initialize a local Git repository and create a commit of the supplied files first, or use a checkout containing this revision. Record that provenance; do not present the resulting local commit as the original research commit.

## Author decisions still needed

Confirm the experimental interpretation, corresponding author/metadata and forms; finalize data availability and have another team member reproduce the main table. Natural drift, retraining policies, serving scalability and adversarial model isolation remain unevaluated. The organizers' specific citation-integrity trigger is still unspecified. No paper or message has been submitted externally by this task.
