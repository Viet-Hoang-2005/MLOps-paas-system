import json
import os
import sys
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from dotenv import dotenv_values


def parse_env_file(env_path: Path) -> dict:
    """Đọc và parse file .env thành dictionary bảo mật qua python-dotenv."""
    if not env_path.exists():
        print(f"Error: Cannot find .env file at {env_path}")
        sys.exit(1)

    raw_data = dotenv_values(env_path)
    # Xử lý ký tự newline bị escaped trong literal string (VD: \n -> dấu xuống dòng thật)
    parsed_data = {}
    for k, v in raw_data.items():
        if v is not None:
            # Khôi phục \n bị thoát thành xuống dòng thực sự cho các loại khóa PEM
            parsed_data[k] = v.replace("\\n", "\n")
        else:
            parsed_data[k] = v
            
    return parsed_data

def update_or_create_secret(client, secret_name: str, secret_dict: dict):
    """Cập nhật giá trị JSON vào AWS Secrets Manager, nếu chưa có thì tạo mới."""
    secret_string = json.dumps(secret_dict, ensure_ascii=False, indent=2)

    try:
        response = client.put_secret_value(
            SecretId=secret_name, SecretString=secret_string
        )
        print(f"Updated Secret: {secret_name}")
        return response
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"Secret {secret_name} does not exist on AWS. Creating a new one...")
            try:
                response = client.create_secret(
                    Name=secret_name,
                    SecretString=secret_string,
                    Description=f"Auto-pushed secret for {secret_name}",
                )
                print(f"Created new Secret: {secret_name}")
                return response
            except ClientError as ce:
                print(f"Error when creating new secret {secret_name}: {ce}")
                raise ce
        else:
            print(f"Error when updating secret {secret_name}: {e}")
            raise e


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Xác định đường dẫn file .env ở thư mục gốc dự án
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"

    print(f"Loading configuration from: {env_file}")
    env_data = parse_env_file(env_file)
    print(f"Read {len(env_data)} environment variables.")

    # Phân nhóm biến cho 3 kho Secret
    aws_keys = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY"
    ]
    github_keys = [
        "GITHUB_REPO",
        "GITHUB_TOKEN",
        "HARBOR_GITHUB_USERNAME",
        "HARBOR_GITHUB_PASSWORD",
    ]
    production_keys = [
        "DB_USER",
        "DB_PASSWORD",
        "GITHUB_TOKEN",
        "GITHUB_REPO",
        "TUNNEL_TOKEN",
        "HARBOR_USERNAME",
        "HARBOR_PASSWORD",
        "DJANGO_SECRET_KEY",
        "JWT_PRIVATE_KEY",
        "JWT_PUBLIC_KEY",
        "CONTROL_PLANE_WEBHOOK_SECRET",
        "ARGO_EVENTS_WEBHOOK_TOKEN",
        "GOOGLE_OAUTH2_CLIENT_ID",
        "GITHUB_OAUTH2_CLIENT_ID",
        "GITHUB_OAUTH2_CLIENT_SECRET",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
    ]

    aws_secrets_payload = {k: env_data[k] for k in aws_keys if k in env_data}
    github_secrets_payload = {k: env_data[k] for k in github_keys if k in env_data}
    production_secrets_payload = {k: env_data[k] for k in production_keys if k in env_data}

    # Lấy Region từ .env hoặc mặc định ap-southeast-1
    region = os.environ.get("AWS_DEFAULT_REGION") or "ap-southeast-1"
    aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

    print(f"Connecting to AWS Secrets Manager at region: {region}...")
    client_kwargs = {"service_name": "secretsmanager", "region_name": region}
    if aws_access_key_id and aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = aws_access_key_id
        client_kwargs["aws_secret_access_key"] = aws_secret_access_key
        print("-> Using AWS credentials read directly from .env file / environment variables.")
    else:
        print("-> No explicit AWS credentials found in .env; falling back to default AWS credential chain (~/.aws/credentials or IAM role)...")

    client = boto3.client(**client_kwargs)

    secrets_mapping = {
        "mlops/aws-secrets": aws_secrets_payload,
        "mlops/github-actions-secrets": github_secrets_payload,
        "mlops/production-secrets": production_secrets_payload,
    }

    print("\nStarting synchronization to AWS cloud:")
    for secret_name, payload in secrets_mapping.items():
        if not payload:
            print(f"Skipping {secret_name} because it does not contain suitable data.")
            continue
        update_or_create_secret(client, secret_name, payload)
        
        print(f"-> Successfully pushed {len(payload)} keys to {secret_name}:")
        for key in payload:
            print(f"     * {key}")

    print("\nSuccess! All configuration is ready on AWS Secrets Manager.")

if __name__ == "__main__":
    main()
