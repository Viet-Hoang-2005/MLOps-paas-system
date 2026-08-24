# Deep-learning serving

This FastAPI worker serves TensorFlow/Keras or other supported deep-learning MLflow artifacts.

- Runtime identity: `PROJECT_ID` and `MODEL_VERSION_ID`.
- Resolve artifact root, nested `MLmodel`, and packaged source directories.
- Put startup model loading behind a monkeypatchable helper.
- A load failure leaves `model=None` and is reflected in health.
- Convert scalar dictionaries, column-oriented dictionaries, lists, and frames into the expected DataFrame/input form.
- Normalize singleton and batch predictions.
- Prediction before a successful load returns a clear runtime error.

Keep the public worker health/predict contract aligned with model-server.
