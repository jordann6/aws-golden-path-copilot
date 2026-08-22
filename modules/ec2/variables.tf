variable "name" {
  type        = string
  description = "Workload name; used as the instance Name prefix."
}

variable "environment" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type        = string
  description = "Graviton family the copilot right-sized to, e.g. t4g.medium."
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
  type        = number
  default     = 1
  description = "Number of hosts to launch (2+ in prod for availability)."
}

variable "auto_stop" {
  type        = bool
  default     = false
  description = "Attach a nightly stop/start schedule (non-prod cost control)."
}

variable "public_ip" {
  type        = bool
  default     = false
  description = "Golden path is always false; hosts live in a private subnet."
}

variable "imdsv2_required" {
  type    = bool
  default = true
}

variable "hardened_ami" {
  type        = bool
  default     = true
  description = "Informational; the AMI itself comes from ami_ssm_parameter."
}

variable "ami_ssm_parameter" {
  type        = string
  description = "SSM parameter holding the CIS-hardened AMI id published by the EC2 Image Builder pipeline (modules/image-builder)."
}

variable "subnet_id" {
  type        = string
  description = "Private subnet to launch into. Supplied by the deploy harness."
}

variable "create_firewall_route" {
  type        = bool
  default     = false
  description = "Whether to write the 0.0.0.0/0 egress route to the shared firewall. A plan-time-known flag (the firewall ENI id itself is only known after apply)."
}

variable "firewall_route_target" {
  type        = string
  default     = null
  description = "ENI id of the shared Palo Alto VM-Series firewall. With create_firewall_route, a 0.0.0.0/0 route to it is created so all egress is inspected."
}

variable "route_table_id" {
  type        = string
  default     = null
  description = "Route table for the private subnet; required to wire the firewall egress route."
}

variable "kms_key_id" {
  type        = string
  default     = null
  description = "KMS key for the encrypted root volume. Null uses the account EBS default key."
}

variable "tags" {
  type    = map(string)
  default = {}
}
