terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 5.0" }
  }
}

locals {
  # Map the right-sizing family hint onto Fargate task size.
  task = {
    "t4g.micro"  = { cpu = 256, memory = 512 }
    "t4g.small"  = { cpu = 512, memory = 1024 }
    "t4g.medium" = { cpu = 1024, memory = 2048 }
    "t4g.large"  = { cpu = 2048, memory = 4096 }
    "m7g.large"  = { cpu = 2048, memory = 8192 }
    "m7g.xlarge" = { cpu = 4096, memory = 16384 }
  }
  sized = lookup(local.task, var.instance_type, { cpu = 512, memory = 1024 })

  # Non-prod stateless services run the bulk of capacity on Spot.
  capacity_provider = var.use_spot ? "FARGATE_SPOT" : "FARGATE"
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name}-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.sized.cpu
  memory                   = local.sized.memory
  runtime_platform {
    cpu_architecture        = "ARM64" # Graviton
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name  = var.name
    image = "public.ecr.aws/nginx/nginx:latest" # placeholder
    portMappings = [{ containerPort = 80 }]
  }])
  tags = var.tags
}

# ECS service + ALB wiring elided; capacity provider shown to make Spot explicit.
output "capacity_provider" { value = local.capacity_provider }
