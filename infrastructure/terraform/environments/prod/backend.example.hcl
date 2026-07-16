# Copy this file to backend.hcl and replace the bucket value before running:
# terraform init -backend-config=backend.hcl

bucket       = "REPLACE_WITH_UNIQUE_TERRAFORM_STATE_BUCKET"
key          = "accessiq/prod/terraform.tfstate"
region       = "us-east-1"
encrypt      = true
use_lockfile = true
