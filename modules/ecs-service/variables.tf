variable "name" { type = string }
variable "environment" { type = string }
variable "instance_type" {
  type        = string
  description = "Right-sizing hint; mapped to Fargate CPU/memory at plan time."
  default     = "t4g.small"
}
variable "min_capacity" {
  type    = number
  default = 1
}
variable "max_capacity" {
  type    = number
  default = 2
}
variable "use_spot" {
  type    = bool
  default = false
}
variable "auto_stop" {
  type    = bool
  default = false
}
variable "storage_gb" {
  type    = number
  default = 0
}
variable "tags" {
  type    = map(string)
  default = {}
}
