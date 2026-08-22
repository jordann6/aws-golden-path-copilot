terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# The CIS-hardened AMI is baked by modules/image-builder and its id published to
# SSM. Reading it here means every host launches from the latest golden AMI
# without the copilot ever hard-coding an ami-* id.
data "aws_ssm_parameter" "ami" {
  name = var.ami_ssm_parameter
}

# Instance role for SSM Session Manager access. No SSH key, no inbound 22.
resource "aws_iam_role" "this" {
  name = "${var.name}-${var.environment}-ec2"
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

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name}-${var.environment}-ec2"
  role = aws_iam_role.this.name
}

# No inbound rules (SSM only); egress open so traffic can reach the firewall.
resource "aws_security_group" "this" {
  name        = "${var.name}-${var.environment}-ec2"
  description = "Hardened host: no inbound, egress inspected by shared firewall."
  vpc_id      = data.aws_subnet.this.vpc_id

  egress {
    description = "All egress (routed through the shared firewall for inspection)."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

data "aws_subnet" "this" {
  id = var.subnet_id
}

resource "aws_instance" "this" {
  count = var.min_capacity

  ami           = data.aws_ssm_parameter.ami.value
  instance_type = var.instance_type
  subnet_id     = var.subnet_id

  associate_public_ip_address = var.public_ip # golden path: false
  iam_instance_profile        = aws_iam_instance_profile.this.name
  vpc_security_group_ids      = [aws_security_group.this.id]
  monitoring                  = true

  # IMDSv2 required (token-backed), hop limit 1.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = var.imdsv2_required ? "required" : "optional"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = var.storage_class
    volume_size = var.storage_gb
    encrypted   = true
    kms_key_id  = var.kms_key_id
  }

  tags = merge(var.tags, { Name = "${var.name}-${var.environment}-${count.index}" })
}

# Egress inspection: default route out of the private subnet points at the
# shared Palo Alto VM-Series firewall's ENI. Created only when the deploy harness
# opts in (the ENI id is known only after apply, so the toggle is a bool flag).
resource "aws_route" "firewall_egress" {
  count = var.create_firewall_route ? 1 : 0

  route_table_id         = var.route_table_id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = var.firewall_route_target
}
