# Secret management CLI

Install dependencies with `python -m pip install -r scripts/requirements.txt`.
Run `python scripts/create_and_push_secrets_to_aws.py` for the interactive menu:
choose **local .env** or **AWS**, then the secret groups. Existing non-empty
values are preserved. Missing internal secrets offer automatic generation or
hidden manual input. Provider credentials (AWS, OAuth, SMTP, Cloudflare, GitHub
and Harbor) must be supplied from the provider; random strings cannot replace them.

Generate the missing Training Fernet key locally:

```powershell
python scripts/create_and_push_secrets_to_aws.py --mode local --keys TRAINING_SECRET_ENCRYPTION_KEY --auto --yes --non-interactive
```

Publish only that key to AWS; generate and save it locally first if missing:

```powershell
python scripts/create_and_push_secrets_to_aws.py --mode aws --keys TRAINING_SECRET_ENCRYPTION_KEY --auto --yes --non-interactive
```

AWS mode merges selected keys into Terraform-owned Secrets Manager containers,
preserving unrelated properties. Training uses `mlops/production-secrets`, matching
the production ExternalSecret. Create the secret containers through Terraform
before publishing. Newly prepared values are saved locally before the AWS write;
if publishing fails, retry the same command without rotating. Multiple target
containers are published separately, so an interrupted run may be partially applied.
Avoid concurrent publishers to the same AWS JSON container.

Other examples:

```powershell
# Audit key names and configured/missing status; never print values
python scripts/create_and_push_secrets_to_aws.py --list

# Local database and Redis credentials, preserving existing values
python scripts/create_and_push_secrets_to_aws.py --mode local --groups 1,2 --auto --yes --non-interactive

# Validate/preview without file writes or any AWS requests
python scripts/create_and_push_secrets_to_aws.py --mode aws --groups 11 --auto --dry-run --non-interactive

# Publish using a named AWS profile and explicit region
python scripts/create_and_push_secrets_to_aws.py --mode aws --groups 11 --profile production --region ap-southeast-1 --yes --non-interactive
```

`--env-file` (`-f`) selects another dotenv file. `--groups` (`-g`) accepts numbers
1–11 or `0` for all; alternatively `--keys` (`-k`) selects exact comma-separated
keys. JWT private/public keys are always managed together. `--auto` (`-a`)
generates supported missing internal secrets; it never overwrites an existing
value. `--yes` approves writes; `--non-interactive` disables input. In unattended
mode, missing values without generation support produce an error before writing.
`--profile` takes precedence over AWS credentials in dotenv; without it, dotenv
credentials (including an optional session token) or the SDK credential chain
are used. No secret values are accepted through CLI arguments or shown in output.

`--rotate` explicitly replaces supported internal credentials (see `--help`).
It does not support rotating the Training encryption key: replacing that key
without migrating encrypted data makes existing Training Secrets unreadable.
Keep a secure backup of this key. For local services to receive a newly configured
key, recreate Control Plane and Celery worker containers; an ordinary restart
does not reload Compose environment variables.

Tests use disposable dotenv files and a mocked AWS client:

```powershell
python -m pytest scripts/tests/test_create_and_push_secrets.py -q
```
