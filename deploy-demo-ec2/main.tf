# Deploy-demo harness for the hardened-compute golden path. Proves the copilot's
# rendered EC2 request stands up a real, correctly-postured host and destroys
# clean. NOT part of the golden path; production is a reviewed PR merged through
# GitOps. This harness supplies only what the ec2 module needs to run in
# isolation (a VPC, a private subnet, a private route table, and a stand-in ENI
# representing the shared Palo Alto VM-Series firewall) and then calls the
# *unmodified* ../modules/ec2 and ../modules/image-builder with the copilot's
# rendered variables.
#
# What is real vs. represented: the Image Builder pipeline is applied for real.
# Actually baking an AMI takes ~30 min and real money for no extra demo value,
# so the golden-AMI SSM parameter the host reads is seeded with the current
# AL2023 arm64 AMI, standing in for a completed pipeline build.

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

# Current AL2023 arm64 AMI (t4g is Graviton/arm64). Stands in for the AMI the
# Image Builder pipeline would publish.
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

# Throwaway network: one public subnet (for the firewall stand-in ENI) and one
# private subnet (for the hardened host). No NAT/IGW attached to the private
# route table: egress is meant to leave via the firewall.
resource "aws_vpc" "demo" {
  cidr_block           = "10.43.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Name = "${var.name}-demo" })
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = cidrsubnet(aws_vpc.demo.cidr_block, 8, 0)
  availability_zone = data.aws_availability_zones.available.names[0]
  tags              = merge(var.tags, { Name = "${var.name}-demo-public" })
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = cidrsubnet(aws_vpc.demo.cidr_block, 8, 1)
  availability_zone = data.aws_availability_zones.available.names[0]
  tags              = merge(var.tags, { Name = "${var.name}-demo-private" })
}

# Private route table the ec2 module writes its 0.0.0.0/0 -> firewall route into.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.demo.id
  tags   = merge(var.tags, { Name = "${var.name}-demo-private" })
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# Stand-in for the shared Palo Alto VM-Series firewall's ENI. In production this
# is the real appliance's interface; here it just proves the egress route wires
# up against the unmodified module.
resource "aws_network_interface" "firewall" {
  subnet_id   = aws_subnet.public.id
  description = "Stand-in for the shared Palo Alto VM-Series firewall ENI."
  tags        = merge(var.tags, { Name = "${var.name}-demo-firewall-eni" })
}

# The golden-AMI parameter the ec2 module reads. Seeded with the real AL2023
# arm64 AMI to represent a completed Image Builder build.
resource "aws_ssm_parameter" "golden_ami" {
  name        = var.ami_ssm_parameter
  type        = "String"
  value       = data.aws_ssm_parameter.al2023_arm64.value
  description = "Demo: current AL2023 arm64 AMI standing in for the pipeline's hardened output."
  tags        = var.tags
}

# The Image Builder pipeline itself, applied for real. Uses a demo-only SSM
# parameter name so it does not collide with the seeded golden_ami above.
module "image_builder" {
  source = "../modules/image-builder"

  name               = var.name
  environment        = var.environment
  ssm_parameter_name = "${var.ami_ssm_parameter}-pipeline"
  tags               = var.tags
  # subnet_id omitted: no build is triggered here, and Image Builder requires a
  # matching security group whenever a subnet is set.
}

# The hardened host, from the unmodified module, with the copilot's rendered
# variables. Depends on the seeded parameter so the data-source read gets a real
# AMI id.
module "host" {
  source = "../modules/ec2"

  name          = var.name
  environment   = var.environment
  region        = var.region
  instance_type = var.instance_type
  storage_gb    = var.storage_gb
  storage_class = var.storage_class
  min_capacity  = var.min_capacity
  auto_stop     = var.auto_stop
  public_ip     = var.public_ip
  imdsv2_required   = var.imdsv2_required
  hardened_ami      = var.hardened_ami
  ami_ssm_parameter = var.ami_ssm_parameter

  subnet_id             = aws_subnet.private.id
  route_table_id        = aws_route_table.private.id
  firewall_route_target = aws_network_interface.firewall.id
  create_firewall_route = true

  tags = var.tags

  depends_on = [aws_ssm_parameter.golden_ami]
}

output "instance_ids" {
  value = module.host.instance_ids
}

output "private_ips" {
  value = module.host.private_ips
}

output "ami_id" {
  value = nonsensitive(module.host.ami_id) # AMI ids are public identifiers
}

output "pipeline_arn" {
  value = module.image_builder.pipeline_arn
}
