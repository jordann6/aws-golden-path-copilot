terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# EC2 Image Builder pipeline that bakes a CIS-hardened AL2023 AMI and publishes
# its id to SSM, where the ec2 module reads it. This is the "golden AMI" factory
# behind the hardened-compute golden path.

# --- Hardening component ----------------------------------------------------
# A minimal CIS-style hardening document layered on top of the AWS-managed
# hardening component below. In a real estate this expands to the full CIS
# benchmark remediation; kept short here so the module stays readable.
resource "aws_imagebuilder_component" "cis" {
  name        = "${var.name}-cis-hardening"
  platform    = "Linux"
  version     = "1.0.0"
  description = "Baseline CIS hardening: disable unused services, enforce auditd, lock down SSH."

  data = yamlencode({
    name          = "cis-hardening"
    schemaVersion = 1.0
    phases = [{
      name = "build"
      steps = [
        {
          name   = "EnforceAuditd"
          action = "ExecuteBash"
          inputs = { commands = ["systemctl enable auditd", "systemctl start auditd"] }
        },
        {
          name   = "DisableUnusedServices"
          action = "ExecuteBash"
          inputs = { commands = ["systemctl disable rpcbind || true", "systemctl disable avahi-daemon || true"] }
        },
        {
          name   = "HardenSSH"
          action = "ExecuteBash"
          inputs = { commands = [
            "sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config",
            "sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config",
          ] }
        },
      ]
    }]
  })

  tags = var.tags
}

# --- Recipe: base image + AWS-managed hardening + our CIS component ----------
resource "aws_imagebuilder_image_recipe" "this" {
  name         = "${var.name}-al2023-cis"
  version      = "1.0.0"
  parent_image = var.parent_image

  # AWS-managed patch baseline, then our CIS hardening layer.
  component {
    component_arn = "arn:aws:imagebuilder:${data.aws_region.current.name}:aws:component/update-linux/x.x.x"
  }
  component {
    component_arn = aws_imagebuilder_component.cis.arn
  }

  block_device_mapping {
    device_name = "/dev/xvda"
    ebs {
      volume_type           = "gp3"
      volume_size           = 30
      encrypted             = true
      delete_on_termination = true
    }
  }

  tags = var.tags
}

# --- Build infrastructure ---------------------------------------------------
resource "aws_iam_role" "builder" {
  name = "${var.name}-imagebuilder"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "builder_imagebuilder" {
  role       = aws_iam_role.builder.name
  policy_arn = "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilder"
}

resource "aws_iam_role_policy_attachment" "builder_ssm" {
  role       = aws_iam_role.builder.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "builder" {
  name = "${var.name}-imagebuilder"
  role = aws_iam_role.builder.name
}

resource "aws_imagebuilder_infrastructure_configuration" "this" {
  name                          = "${var.name}-infra"
  instance_profile_name         = aws_iam_instance_profile.builder.name
  instance_types                = var.instance_types
  subnet_id                     = var.subnet_id
  terminate_instance_on_failure = true
  tags                          = var.tags
}

resource "aws_imagebuilder_distribution_configuration" "this" {
  name = "${var.name}-dist"

  distribution {
    region = data.aws_region.current.name
    ami_distribution_configuration {
      name     = "${var.name}-al2023-cis-{{ imagebuilder:buildDate }}"
      ami_tags = merge(var.tags, { Hardened = "cis" })
    }
  }
}

# --- Pipeline ---------------------------------------------------------------
resource "aws_imagebuilder_image_pipeline" "this" {
  name                             = "${var.name}-al2023-cis"
  image_recipe_arn                 = aws_imagebuilder_image_recipe.this.arn
  infrastructure_configuration_arn = aws_imagebuilder_infrastructure_configuration.this.arn
  distribution_configuration_arn   = aws_imagebuilder_distribution_configuration.this.arn

  schedule {
    schedule_expression = var.schedule_expression
  }

  image_tests_configuration {
    image_tests_enabled = true
  }

  tags = var.tags
}

# The ec2 module reads this parameter for the AMI id. Image Builder updates it
# on each successful build via an SSM automation / EventBridge target (wired in
# the deploy harness); the resource here reserves the name with a placeholder.
resource "aws_ssm_parameter" "ami" {
  name        = var.ssm_parameter_name
  type        = "String"
  value       = "ami-placeholder-updated-by-pipeline"
  description = "Latest CIS-hardened AL2023 AMI id (updated by the Image Builder pipeline)."
  tags        = var.tags

  lifecycle {
    ignore_changes = [value] # the pipeline owns the value after first apply
  }
}

data "aws_region" "current" {}
