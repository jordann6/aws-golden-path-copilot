# Deploy-demo harness: proves the copilot's rendered request actually stands up
# real AWS infrastructure and destroys clean. It is NOT part of the golden path;
# the production flow is a reviewed pull request whose merge triggers Terraform
# through GitOps. This harness only supplies the networking the RDS module needs
# (a DB subnet group + security group) and then calls the *unmodified* vetted
# module with the copilot's rendered tfvars, so the receipt reflects real output.
#
# Usage: copy one rendered `out/<id>.auto.tfvars.json` in here (Terraform
# auto-loads *.auto.tfvars.json), then `terraform apply` / `terraform destroy`.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_availability_zones" "available" {
  state = "available"
}

# Throwaway network: private-only, no IGW/NAT. RDS needs subnets in >=2 AZs.
resource "aws_vpc" "demo" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Name = "${var.name}-demo" })
}

resource "aws_subnet" "demo" {
  count             = 2
  vpc_id            = aws_vpc.demo.id
  cidr_block        = cidrsubnet(aws_vpc.demo.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = merge(var.tags, { Name = "${var.name}-demo-${count.index}" })
}

resource "aws_db_subnet_group" "demo" {
  name       = "${var.name}-${var.environment}-demo"
  subnet_ids = aws_subnet.demo[*].id
  tags       = var.tags
}

# No ingress: the demo only proves the instance provisions and tears down.
resource "aws_security_group" "demo" {
  name_prefix = "${var.name}-${var.environment}-demo-"
  vpc_id      = aws_vpc.demo.id
  tags        = var.tags

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "db" {
  source = "../modules/rds"

  name                = var.name
  environment         = var.environment
  engine              = var.engine
  instance_type       = var.instance_type
  storage_gb          = var.storage_gb
  storage_class       = var.storage_class
  multi_az            = var.multi_az
  deletion_protection = var.deletion_protection
  auto_stop           = var.auto_stop
  tags                = var.tags

  db_subnet_group_name   = aws_db_subnet_group.demo.name
  vpc_security_group_ids = [aws_security_group.demo.id]
}

output "db_endpoint" {
  value = module.db.endpoint
}

output "db_identifier" {
  value = module.db.identifier
}
