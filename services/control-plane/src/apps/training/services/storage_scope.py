from infrastructure.storage.paths import training_job_prefix


def expected_training_uris(job, bucket):
    prefix = training_job_prefix(
        job.project.owner.tenant_id,
        job.project.public_id,
        job.public_id,
    )
    return {
        "code": f"s3://{bucket}/{prefix}/input/code/source.zip",
        "data": f"s3://{bucket}/{prefix}/input/data/train.csv",
        "output": f"s3://{bucket}/{prefix}/output/model.tar.gz",
        "mlflow": f"s3://{bucket}/{prefix}/mlflow/",
    }


def validate_training_uri(job, bucket, kind, uri):
    expected = expected_training_uris(job, bucket)[kind]
    if uri != expected:
        raise ValueError(f"Training {kind} URI is outside the job-scoped storage path.")
    return uri
