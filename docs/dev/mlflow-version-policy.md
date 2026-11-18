# Managed MLflow version policy

The platform-managed Control Plane, Evidently, Model Packager, machine-learning
serving, deep-learning serving, and Training Runner images use `mlflow==3.18.0`.
Keep these pins aligned when changing the MLflow tracking API or model package
format. The runtime runner dependency is platform-owned; uploaded Training
Workspace requirements remain user-controlled and are not rewritten.

Generated MLflow model packages pin the full `mlflow` distribution to 3.18.0.
Scikit-learn packages use cloudpickle serialization and PyTorch packages use
pickle serialization explicitly so that MLflow upgrades do not silently switch
the model format. Imported model-package ZIP files are kept unchanged, while
their MLflow family pins are ignored during platform-side validation and serving
image dependency installation. Other model dependencies are still validated and
installed normally.

`MLFLOW_TRACKING_URI` is the base Control Plane URL, for example
`http://control-plane:8000`. The MLflow SDK adds `/api/2.0/mlflow` itself. The
Control Plane continues to expose its job-scoped Tracking API at that path and
authorizes calls with the job capability token.

This is a local code/dependency contract. It does not imply a deployed MLflow
Tracking Server or a production rollout.
