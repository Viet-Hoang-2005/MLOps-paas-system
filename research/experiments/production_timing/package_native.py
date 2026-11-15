"""Package the frozen booster with the supported native MLflow XGBoost loader."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
import xgboost as xgb
from mlflow.models import ModelSignature
from mlflow.types import ColSpec, Schema


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    model_path = args.bundle / 'model/baseline.ubj'
    manifest = json.loads((args.bundle / 'manifest.json').read_text())
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == manifest['model_sha256']
    model = xgb.XGBClassifier()
    model.load_model(model_path)
    package_name = 'native-cpu-model' if args.cpu else 'native-model'
    destination = args.output / package_name
    signature = ModelSignature(inputs=Schema([ColSpec('double', name) for name in manifest['features']]),
                               outputs=Schema([ColSpec('long')]))
    requirements = ['mlflow==3.11.1', 'xgboost==3.2.0', 'pandas==2.3.3', 'numpy==2.0.2']
    if args.cpu:
        requirements = ['mlflow==3.11.1', 'xgboost-cpu==3.2.0', 'pandas==2.2.1', 'numpy==1.26.4']
    mlflow.xgboost.save_model(model, destination, signature=signature, model_format='ubj',
                             pip_requirements=requirements)
    packaged = mlflow.pyfunc.load_model(destination)
    checked = 0
    max_probability_difference = 0
    for window in sorted((args.bundle / 'windows').iterdir()):
        inputs = pd.read_csv(window / 'features.csv')[manifest['features']].astype('float64')
        expected = pd.read_csv(args.bundle / 'scoring' / (window.name + '.csv'))
        predictions = np.asarray(packaged.predict(inputs)).astype('int64')
        assert np.array_equal(predictions, expected.expected_pred_binary.to_numpy()), window.name
        probabilities = model.predict_proba(inputs)[:, 1]
        difference = float(np.max(np.abs(probabilities - expected.expected_prob_attack.to_numpy())))
        max_probability_difference = max(max_probability_difference, difference)
        assert difference <= 1e-7
        checked += len(inputs)
    archive_path = args.output / (package_name + '.zip')
    with ZipFile(archive_path, 'w', ZIP_DEFLATED) as archive:
        for path in destination.rglob('*'):
            if path.is_file():
                archive.write(path, path.relative_to(destination).as_posix())
    result = {
        'source_model_sha256': manifest['model_sha256'], 'predictions_checked': checked,
        'label_mismatches': 0, 'max_probability_difference_from_rounded_scoring': max_probability_difference,
        'native_loader': 'mlflow.xgboost', 'source_artifacts_modified': False,
        'requirements': requirements,
        'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
    }
    (args.output / (package_name + '-verification.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
