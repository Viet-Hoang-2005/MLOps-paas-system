"""MLflow model-from-code adapter; preserves the frozen >= 0.5 decision rule."""
import mlflow
import numpy as np
import xgboost as xgb


class FrozenNIDS(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.booster = xgb.Booster()
        self.booster.load_model(context.artifacts["baseline"])

    def predict(self, context, model_input, params=None):
        frame = model_input[self.booster.feature_names].astype("float64")
        probabilities = self.booster.predict(xgb.DMatrix(frame))
        return (np.asarray(probabilities) >= 0.5).astype("int64")


mlflow.models.set_model(FrozenNIDS())
