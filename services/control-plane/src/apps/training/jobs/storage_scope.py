from infrastructure.storage.paths import tenant_training_job_prefix, training_job_prefix


def training_prefix_for(job):
    owner = job.owner if job.owner_id else job.project.owner
    if job.storage_layout == "tenant":
        return tenant_training_job_prefix(owner.tenant_id, job.public_id)
    project_id = job.storage_project_id or (job.project.public_id if job.project_id else None)
    if not project_id:
        raise ValueError("Project-scoped training storage has no original project identity.")
    return training_job_prefix(owner.tenant_id, project_id, job.public_id)


def expected_training_uris(job, bucket):
    prefix = training_prefix_for(job)
    mlflow_prefix = f"{prefix}/mlflow/artifacts/"
    input_prefix = f"{prefix}/input"
    if job.submission_token:
        input_prefix += f"/submissions/{job.submission_token}"
    return {
        "code": f"s3://{bucket}/{input_prefix}/code/source.zip",
        "data": f"s3://{bucket}/{input_prefix}/data/data.zip",
        "output": f"s3://{bucket}/{prefix}/output/model.tar.gz",
        "mlflow": f"s3://{bucket}/{mlflow_prefix}",
    }


def validate_training_uri(job, bucket, kind, uri):
    expected = expected_training_uris(job, bucket)[kind]
    if uri != expected:
        raise ValueError(f"Training {kind} URI is outside the job-scoped storage path.")
    return uri
