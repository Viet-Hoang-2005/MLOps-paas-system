# Machine-learning serving

This FastAPI worker serves sklearn/XGBoost-compatible MLflow artifacts.

- Runtime identity: `PROJECT_ID` and `MODEL_VERSION_ID`.
- Resolve root/nested `MLmodel` and prefer a complete prebuilt artifact.
- Cache models by version marker; reload when the marker changes.
- Read expected features from MLflow signature and preserve column order.
- Support label mappings from JSON, pickle, or list forms.
- Normalize NumPy, Series, list, and scalar predictions.
- Compute confidence when `predict_proba` exists.
- Health reports IDs and load state.
- Missing features or feature mismatch map to client errors; unexpected runtime failures map to server errors.

Do not perform network/storage loading at import time.
