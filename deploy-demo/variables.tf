# Root variables mirror the copilot's rendered tfvars keys so a dropped-in
# out/<id>.auto.tfvars.json loads without edits. The RDS-irrelevant knobs
# (use_spot, min/max_capacity) are declared here only to consume the file
# cleanly; they belong to the ECS golden path.

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

variable "engine" {
  type    = string
  default = "postgres"
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

variable "multi_az" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "auto_stop" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}

# Declared to absorb the rendered tfvars; not used by the RDS path.
variable "use_spot" {
  type    = bool
  default = false
}

variable "min_capacity" {
  type    = number
  default = 1
}

variable "max_capacity" {
  type    = number
  default = 1
}
