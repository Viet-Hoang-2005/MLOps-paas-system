import os
import boto3
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.session import Session


def get_required_env(name):
    value = os.environ.get(name, "").strip()
    if not value or value.lower() in {"none", "null"}:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main():
    # Khởi tạo các biến môi trường cấu hình từ GitHub Actions
    role_arn = get_required_env("AWS_SAGEMAKER_ROLE_ARN")
    bucket = get_required_env("AWS_BUCKET_NAME")
    prefix = get_required_env("S3_TRAINING_DATA_PREFIX")
    target_csv = get_required_env("TARGET_CSV")
    model_version = get_required_env("MODEL_VERSION")
    mlflow_uri = get_required_env("MLFLOW_TRACKING_URI")
    mlflow_user = get_required_env("MLFLOW_TRACKING_USERNAME")
    mlflow_pass = get_required_env("MLFLOW_TRACKING_PASSWORD")
    mlflow_model_name = get_required_env("MLFLOW_MODEL_NAME")
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")
    instance_type = os.environ.get("SAGEMAKER_INSTANCE_TYPE", "ml.m5.large")
    max_run = int(os.environ.get("SAGEMAKER_MAX_RUN", "3600"))
    max_wait = int(os.environ.get("SAGEMAKER_MAX_WAIT", "7200"))
    output_prefix = (
        os.environ.get("SAGEMAKER_OUTPUT_PREFIX", "tenants").strip().strip("/")
    )
    framework_version = os.environ.get("SAGEMAKER_SKLEARN_FRAMEWORK_VERSION", "1.2-1")
    py_version = os.environ.get("SAGEMAKER_PY_VERSION", "py3")
    use_spot = get_bool_env("SAGEMAKER_USE_SPOT", True)

    # Khởi tạo SageMaker Session
    boto_session = boto3.Session(region_name=region)
    sagemaker_session = Session(boto_session=boto_session)

    # Chuẩn bị Environment Variables để tiêm vào Container huấn luyện
    training_env = {
        "TARGET_CSV": target_csv,
        "MODEL_VERSION": model_version,
        "AWS_BUCKET_NAME": bucket,
        "S3_TRAINING_DATA_PREFIX": prefix,
        "MLFLOW_TRACKING_URI": mlflow_uri,
        "MLFLOW_TRACKING_USERNAME": mlflow_user,
        "MLFLOW_TRACKING_PASSWORD": mlflow_pass,
        "MLFLOW_MODEL_NAME": mlflow_model_name,
    }

    print(f"Triggering SageMaker Training Job for {model_version}...")
    output_path = f"s3://{bucket}/{output_prefix}/sagemaker-output/{model_version}/"

    # Sử dụng SKLearn framework base image, hỗ trợ tự động cài requirements.txt
    estimator = SKLearn(
        entry_point="train.py",
        source_dir="sagemaker",
        role=role_arn,
        instance_count=1,
        instance_type=instance_type,
        framework_version=framework_version,
        py_version=py_version,
        sagemaker_session=sagemaker_session,
        output_path=output_path,
        environment=training_env,
        base_job_name=f"mlops-paas-{model_version.replace('.', '-')}",
        use_spot_instances=use_spot,
        max_run=max_run,
        max_wait=max_wait,
    )

    # Đường dẫn thư mục chứa dữ liệu trên S3
    training_data_uri = f"s3://{bucket}/{prefix}"
    print(f"Training data URI: {training_data_uri}")
    print(f"SageMaker output path: {output_path}")

    # Bắt đầu Training Job (wait=False để GitHub Actions kết thúc ngay lập tức, Job chạy ngầm trên AWS)
    estimator.fit({"train": training_data_uri}, wait=False)

    print("Training Job launched successfully in the background!")
    print(f"Job Name: {estimator.latest_training_job.name}")


if __name__ == "__main__":
    main()
