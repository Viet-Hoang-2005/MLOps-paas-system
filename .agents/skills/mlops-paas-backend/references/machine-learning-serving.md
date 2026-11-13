# Machine Learning Serving

The Machine Learning Serving worker (`services/machine-learning-serving/`) is a dedicated, stateless inference engine built with FastAPI for classical tabular ML models (Scikit-Learn, XGBoost, LightGBM, CatBoost) packaged as MLflow artifacts.

## Core Responsibilities

1. **Runtime Identity:** Operates using `PROJECT_ID` and `MODEL_VERSION_ID`.
2. **Artifact Loading & In-Memory Cache:**
   - Loads MLflow models from S3 (`MODEL_URI`) or local filesystem upon startup or first request.
   - Recognizes `MLmodel` specifications and caches active model instances in `MODEL_CACHE`.
   - Never loads artifacts over the network at module import time.
3. **Feature Column Alignment:**
   - Extracts expected feature schema from the MLflow Model Signature.
   - Validates incoming JSON feature dictionaries and reorders columns to strictly match the matrix column order expected by the trained model.
4. **Inference & Confidence Scoring:**
   - Calls `model.predict(input_df)` and normalizes predictions across NumPy arrays, Series, lists, and scalar values.
   - Calculates `confidence` scores (ranging `0.0` to `1.0`) via `predict_proba` when supported by the classifier.
5. **Health Reporting:** Endpoint `GET /health` reports load state, `model_version_id`, `project_id`, and engine metadata.
6. **HTTP Error Mapping:**
   - Missing required features, column mismatches, or malformed data return `HTTP 400 Bad Request`.
   - Unexpected runtime crashes return `HTTP 500 Internal Server Error`.
