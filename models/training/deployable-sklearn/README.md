# Deployable sklearn training sample

This sample validates the Train-to-Deploy E2E flow.

## Files

| File | Purpose |
|---|---|
| `train.py` | Reads CSV from `SM_CHANNEL_TRAIN`, trains a sklearn pipeline, writes artifacts to `SM_MODEL_DIR` |
| `requirements.txt` | Minimal Python dependencies |
| `train.csv` | Training dataset - includes feature columns **and** `label` column |
| `predict.csv` | Prediction-only dataset - feature columns **only**, no label |
| `source.zip` | Generated upload zip, created by the command below |

## CSV format

### train.csv (for training)

```
f1,f2,f3,label
1.0,2.0,3.0,normal
5.0,4.9,6.0,attack
```

The `label` column is the target/ground truth used during training. It is **not** a feature.

### predict.csv (for Model Testing)

```
f1,f2,f3
1.0,2.0,3.0
5.0,4.9,6.0
```

Only feature columns. The Model Testing UI automatically ignores common label columns
(`label`, `target`, `y`, `class`, `ground_truth`, `true_label`) - so uploading `train.csv`
directly in Model Testing also works correctly.

## Expected training output (inside `model.tar.gz`)

- `model.pkl`
- `label_mapping.json`
- `model_metadata.json`

## Create `source.zip` for upload

```powershell
Compress-Archive -Path examples/training/deployable-sklearn/train.py `
  -DestinationPath examples/training/deployable-sklearn/source.zip -Force
```

## Upload on `/dashboard/model-training`

| Field | File |
|---|---|
| Source zip | `source.zip` |
| Requirements | `requirements.txt` |
| Training data | `train.csv` |

## Model Testing

After Train-to-Deploy completes:

1. Go to **Model Testing**.
2. Select `deployable-sklearn-demo`.
3. Upload either `train.csv` (label auto-excluded) or `predict.csv` (features only).
4. Click **Run test**.
5. Expected: predictions show `normal` or `attack` with confidence and match/mismatch badge.

> **Note:** If you upload `train.csv`, the UI shows an amber badge:  
> `Auto-excluding: label` - confirming the label column is not sent as a feature.
