# Citation audit for the revised CSoNet short paper

Scope: the 17 references retained in the revised manuscript, their bibliographic identity/version, and the specific broad claim for which they are cited. Checked against publisher pages, author/institution copies, and versioned arXiv records on 26–27 September 2026. This is not a finding about which item triggered the reviewer's unspecified “citation-integrity trigger”; that issue still needs clarification from the organizers if available.

## Corrections and claim changes

- `kreuzberger2023mlops`: corrected **M.** to **D. Kreuzberger**, and Kühl's spelling; confirmed IEEE Access 11, 31866–31879 (2023), DOI 10.1109/ACCESS.2023.3262138.
- `subramanya2022devops`: replaced the incorrect author list with **R. Subramanya, S. Sierla, V. Vyatkin**; added article 9851 and DOI 10.3390/app12199851.
- `renggli2021data`: corrected the authors/order to **C. Renggli, L. Rimanic, N. M. Gürel, B. Karlaš, W. Wu, C. Zhang**; explicitly cites arXiv v1.
- `gama2014survey`: added article 44 and DOI; corrected diacritics.
- Recent preprints now identify exact arXiv versions. The SSF entry uses v4 (2025), avoiding confusion with its first submission in 2024. HarmonE/SSF are cited as preprint versions, rather than mixing preprint identifiers with unverified proceedings pagination.
- Added the original BH reference for the correction used in the experiment.
- Removed the broad tool-gap comparison table. Old source descriptions do not establish that current products lack tenancy, monitoring or lifecycle capabilities. Related Work now describes the cited studies and explicitly avoids a superiority claim.

## Retained references and support

| Key | Primary source inspected | Claim supported in this manuscript / action |
|---|---|---|
| `kreuzberger2023mlops` | [Institutional copy of published article](https://epub.uni-bayreuth.de/id/eprint/7577/1/Machine_Learning_Operations_MLOps_Overview_Definition_and_Architecture.pdf), title page/abstract and component discussion | MLOps components/workflows. Corrected author initial and added DOI. Does not prove our registry is novel. |
| `sculley2015debt` | [NeurIPS proceedings](https://papers.nips.cc/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html), author list/abstract | Data dependencies and technical debt. Retained. |
| `amershi2019software` | [Microsoft Research paper](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/03/amershi-icse-2019_Software_Engineering_for_Machine_Learning.pdf), first page/abstract; [publication record](https://www.microsoft.com/en-us/research/publication/software-engineering-for-machine-learning-a-case-study/?lang=zh-cn) | Data/model/software engineering concerns. Retained; venue abbreviated ICSE-SEIP. |
| `subramanya2022devops` | [Aalto author institution record](https://research.aalto.fi/en/publications/from-devops-to-mlops-overview-and-application-to-electricity-mark/) | MLOps overview and electricity-forecasting application. Replaced wrong authors. Publisher direct fetch was rate-limited; institutional record supplies metadata. |
| `renggli2021data` | [Author-submitted arXiv v1](https://arxiv.org/abs/2102.07750v1), authors/abstract | Data quality propagation through MLOps. Corrected authors, kept explicit preprint identity. |
| `baylor2017tfx` | [Google Research publication](https://research.google/pubs/tfx-a-tensorflow-based-production-scale-machine-learning-platform/) and [author paper](https://storage.googleapis.com/gweb-research2023-media/pubtools/4795.pdf) | Integrated validation, training, serving. Google page presents authors in a different display order; paper is the reference for the Baylor-first citation. No comparative claim against our prototype. |
| `mlflow` | [Author-hosted original paper](https://people.eecs.berkeley.edu/~matei/papers/2018/ieee_mlflow.pdf), abstract/Sections 1–2 | Tracking, reproducibility and deployment interfaces in the 2018 paper. Removed the earlier implication that this citation establishes modern registry feature coverage. |
| `crankshaw2017clipper` | [USENIX paper and BibTeX](https://www.usenix.org/conference/nsdi17/technical-sessions/presentation/crankshaw) | Low-latency online serving; authors/year/pages confirmed. Does not establish our latency/scalability. |
| `Bhatt2025HarmonE` | [arXiv v1](https://arxiv.org/abs/2505.13693v1), authors/abstract/version | Self-adaptive sustainable MLOps approach. Cited as preprint; no extrapolation of their evaluated benefits to our system. |
| `MarcosMercade2026MLOpsFrameworks` | [arXiv v1](https://arxiv.org/abs/2601.20415v1), authors/abstract | Empirical comparison of MLOps workflow tools. No claim that its two ML scenarios benchmark our NIDS framework. |
| `gama2014survey` | [Coauthor institutional publication record](https://research.tue.nl/en/publications/a-survey-on-concept-drift-adaptation/) | Survey of changes in predictive relations and adaptation. Article 44, 46(4), 37 pages, DOI confirmed. Direct ACM retrieval unavailable; institutional abstract supports the narrow citation. |
| `webb2016drift` | [Springer article](https://link.springer.com/article/10.1007/s10618-015-0448-4), abstract and bibliographic record | Characterization of forms of drift. Does not identify concept drift in our generated windows. |
| `Zhang2025SSFNIDS` | [arXiv v4](https://arxiv.org/abs/2412.16264v4), authors/abstract/history | SSF investigates continual-learning NIDS updates. Unlike that study, ours keeps a model fixed; no method comparison is claimed. |
| `xgboost` | [Author-submitted XGBoost paper](https://arxiv.org/abs/1603.02754) | Identity of the tree-boosting method used as baseline. No cited claim that our parameter setting is optimal. |
| `cicids` | [UNB dataset page](https://www.unb.ca/cic/datasets/ids-2017.html) and [SCITEPRESS record](https://www.scitepress.org/Papers/2018/66398/) | Original CICIDS2017 provenance/paper identity. Does not verify the third-party preprocessed derivative or our full download chain. |
| `sommer2010closedworld` | [Author-hosted paper](https://www.icir.org/robin/papers/oakland10-ml.pdf), abstract/introduction | Deployment context/generalization concerns in ML NIDS. Does not establish drift in this experiment. |
| `bh1995` | [Publisher record](https://rss.onlinelibrary.wiley.com/doi/10.1111/j.2517-6161.1995.tb02031.x) | Original BH procedure. Its guarantees are not asserted for dataset-level alerts or arbitrary correlated/tied features in our setting. |

Kaggle URLs are retained as data-source links supplied by the team. The pages were reachable but their body/version metadata was not exposed by the browser extraction. Thus dataset version, license and byte-identical acquisition remain pending; the paper explicitly states this limitation.

## References removed from the shorter manuscript

`john2021towards`, `zhou2020pipeline`, `polyzotis2017data`, and `kubernetes` were removed together with redundant maturity/platform/infrastructure discussion. This is an editorial scope reduction, not a determination that these papers are invalid. A full metadata audit of those unused entries is not claimed. The original reference list remains recoverable from Git history.

## Remaining author checks

Compare this local revision with the actual submitted PDF; request specifics about the citation-integrity trigger if the portal provides no detail. Confirm conference preferences for preprints/DOI formatting in the final source package. A metadata/claim audit cannot certify the absence of every citation-integrity issue in an unseen submitted version.
