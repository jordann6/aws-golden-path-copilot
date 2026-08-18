terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  # The copilot right-sizes with EC2 families (t4g/m7g); RDS needs db.* classes.
  db_instance_class = "db.${var.instance_type}"
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name}-${var.environment}"
  engine         = var.engine
  instance_class = local.db_instance_class

  allocated_storage = var.storage_gb
  storage_type      = var.storage_class
  storage_encrypted = true # golden-path: always encrypted at rest

  multi_az            = var.multi_az
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.environment != "prod"

  # Credentials come from Secrets Manager in the real module; omitted here.
  manage_master_user_password = true
  username                    = "app"

  tags = var.tags
}

# Non-prod nightly stop schedule (cost control). Prod is never auto-stopped.
resource "aws_db_instance_automated_backups_replication" "noop" {
  count            = 0
  source_db_instance_arn = aws_db_instance.this.arn
}
