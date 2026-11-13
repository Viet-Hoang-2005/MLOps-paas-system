# Deep Learning Serving

The Deep Learning Serving worker (`services/deep-learning-serving/`) is a dedicated inference engine built on **BentoML** and **MLflow PyFunc** for serving deep learning models (PyTorch, TensorFlow, Keras, HuggingFace Transformers).

## Core Responsibilities

1. **Runtime Identity:** Operates using `PROJECT_ID` and `MODEL_VERSION_ID`.
2. **BentoML Service Lifecycle:**
   - Managed via BentoML service decorator `@bentoml.service(resources={"cpu": "2"}, traffic={"timeout": 60})`.
   - Startup loading is encapsulated in a helper (`load_runtime_model`), making it easily monkeypatchable in unit tests.
3. **Fault-Tolerant Startup:**
   - If model artifact download or loading fails during startup, the service logs the error and sets `self.model = None` rather than crashing the container.
   - Endpoint `GET /health` reports `model_loaded: false`, allowing orchestrators to observe readiness.
4. **Universal Tensor Input/Output Normalization:**
   - Converts diverse input payloads (scalar dicts, column-oriented dicts, nested lists, and DataFrames) into appropriate tensor/array inputs for `pyfunc.predict()`.
   - Normalizes deep learning tensor outputs (PyTorch Tensors, TF Tensors, NumPy arrays) into JSON-serializable structures.
5. **Inference Execution:**
   - Rejects prediction requests with a clear runtime error if the model failed to load.
   - Exposes `/predict` and `/health` wrapped with `RequestLoggingMiddleware` for context-aware logging.
