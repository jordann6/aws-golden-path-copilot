output "instance_ids" {
  value = aws_instance.this[*].id
}

output "private_ips" {
  value = aws_instance.this[*].private_ip
}

output "security_group_id" {
  value = aws_security_group.this.id
}

output "ami_id" {
  value       = data.aws_ssm_parameter.ami.value
  description = "The CIS-hardened AMI the hosts launched from."
  sensitive   = true # inherited from the SSM parameter read
}
