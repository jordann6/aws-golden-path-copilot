variable "name" {
  type        = string
  description = "Workload name; used as the DB identifier prefix."
}

variable "environment" {
  type = string
}

variable "engine" {
  type    = string
  default = "postgres"
}

variable "instance_type" {
  type        = string
  description = "RDS instance class, e.g. db.t4g.medium. The copilot passes an "
  # note: copilot emits an EC2-style family (t4g/m7g); map to db.* at plan time
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
  type        = bool
  default     = false
  description = "Attach a nightly stop/start schedule (non-prod cost control)."
}

variable "tags" {
  type    = map(string)
  default = {}
}
