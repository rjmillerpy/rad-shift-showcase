# Placeholder values for `terraform plan` in $0 mode. Nothing here is a secret:
# secrets come from SSM Parameter Store (see locals.tf).
api_hostname       = "api.radshift.example.com"
app_url            = "https://radshift.example.com"
backend_image_tag  = "placeholder"
frontend_image_tag = "placeholder"
db_host            = "db.placeholder.internal"
from_email         = "noreply@radshift.example.com"
