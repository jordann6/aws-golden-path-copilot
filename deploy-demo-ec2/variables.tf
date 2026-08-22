# Root variables mirror the copilot's rendered compute tfvars keys so a
# dropped-in out/<id>.auto.tfvars.json loads without edits. Keys that belong to
# other golden paths (multi_az, deletion_protection, use_spot, max_capacity,
# firewall_inspected) are declared only to consume the file cleanly.

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type = string
}

variable "storage_gb" {
  type    = number
  default = 20
}

variable "storage_class" {
  type    = string
  default = "gp3"
}

variable "min_capacity" {
  type    = number
  default = 1
}

variable "auto_stop" {
  type    = bool
  default = false
}

variable "public_ip" {
  type    = bool
  default = false
}

variable "imdsv2_required" {
  type    = bool
  default = true
}

variable "hardened_ami" {
  type    = bool
  default = true
}

variable "ami_ssm_parameter" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

# Declared to absorb the rendered tfvars; not used by the compute path here.
variable "multi_az" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "use_spot" {
  type    = bool
  default = false
}

variable "max_capacity" {
  type    = number
  default = 1
}

variable "firewall_inspected" {
  type    = bool
  default = true
}
