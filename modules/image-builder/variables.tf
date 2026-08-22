variable "name" {
  type        = string
  default     = "golden-path"
  description = "Prefix for the Image Builder resources."
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "parent_image" {
  type        = string
  default     = "arn:aws:imagebuilder:us-east-1:aws:image/amazon-linux-2023-x86/x.x.x"
  description = "Base image the hardening components run on top of. Use the ARM64 AL2023 image ARN for Graviton hosts."
}

variable "instance_types" {
  type        = list(string)
  default     = ["t3.medium"]
  description = "Build instance type(s) used only while baking the AMI."
}

variable "subnet_id" {
  type        = string
  default     = null
  description = "Subnet for the transient build instance. Null uses the default VPC."
}

variable "ssm_parameter_name" {
  type        = string
  default     = "/golden-path/ami/staging/al2023-cis"
  description = "SSM parameter the pipeline writes the output AMI id to. The ec2 module reads this same name."
}

variable "schedule_expression" {
  type        = string
  default     = "cron(0 6 ? * mon *)"
  description = "Rebuild cadence so the golden AMI stays patched (weekly by default)."
}

variable "tags" {
  type    = map(string)
  default = {}
}
