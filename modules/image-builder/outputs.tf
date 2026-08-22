output "pipeline_arn" {
  value = aws_imagebuilder_image_pipeline.this.arn
}

output "recipe_arn" {
  value = aws_imagebuilder_image_recipe.this.arn
}

output "ssm_parameter_name" {
  value       = aws_ssm_parameter.ami.name
  description = "SSM parameter the ec2 module reads for the hardened AMI id."
}
