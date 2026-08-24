import { buildStoredZip, downloadFile } from './trainingZip';

const textEncoder = new TextEncoder();

const sampleTrainPy = `import os
import glob
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier


def main():
    train_dir = os.environ["SM_CHANNEL_TRAIN"]
    model_dir = os.environ["SM_MODEL_DIR"]

    csv_files = glob.glob(os.path.join(train_dir, "*.csv"))
    if not csv_files:
        raise FileNotFoundError("No CSV file found in SM_CHANNEL_TRAIN")

    df = pd.read_csv(csv_files[0])
    target = "label" if "label" in df.columns else df.columns[-1]

    X = df.drop(columns=[target])
    y = df[target]

    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X, y)

    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, "model.joblib"))


if __name__ == "__main__":
    main()
`;

const sampleRequirements = `joblib
pandas
scikit-learn
`;

const sampleTrainCsv = `f1,f2,f3,label
1.0,2.0,3.0,0
1.2,2.1,3.1,0
5.0,4.9,6.0,1
5.2,5.1,6.2,1
0.8,2.0,2.9,0
5.4,5.2,6.5,1
`;

export const downloadSampleTrainingTemplate = async () => {
  const sourceZip = buildStoredZip(
    [
      { name: 'train.py', data: textEncoder.encode(sampleTrainPy) },
    ],
    'source.zip',
  );
  const file = buildStoredZip(
    [
      { name: 'source.zip', data: new Uint8Array(await sourceZip.arrayBuffer()) },
      { name: 'requirements.txt', data: textEncoder.encode(sampleRequirements) },
      { name: 'train.csv', data: textEncoder.encode(sampleTrainCsv) },
    ],
    'mlops-training-template.zip',
  );
  downloadFile(file);
};
