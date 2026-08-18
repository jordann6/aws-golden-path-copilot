variable "name" { type = string }
variable "environment" { type = string }
variable "bucket_name" {
  type    = string
  default = ""
}
variable "versioning" {
  type    = bool
  default = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
