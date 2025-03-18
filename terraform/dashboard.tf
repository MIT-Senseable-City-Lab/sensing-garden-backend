# ECR Repository for Dashboard Docker Image
resource "aws_ecr_repository" "dashboard" {
  name                 = "sensing-garden-dashboard"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# App Runner service
resource "aws_apprunner_service" "dashboard" {

  service_name = "sensing-garden-dashboard"

  source_configuration {
    image_repository {
      image_configuration {
        port = "5052" # Using the port that Flask runs on by default
        runtime_environment_variables = {
          "API_URL" = aws_apigatewayv2_api.http_api.api_endpoint,
          "IMAGES_BUCKET" = "sensing-garden-images",
          "PYTHONPATH" = "/app/dashboard" # Ensure Python can find modules in the dashboard directory
        }
      }
      image_identifier      = "${aws_ecr_repository.dashboard.repository_url}:latest"
      image_repository_type = "ECR"
    }
    auto_deployments_enabled = false # We'll build and push Docker images manually
  }

  instance_configuration {
    cpu = "1024"
    memory = "2048"
  }

  health_check_configuration {
    path = "/"
    protocol = "HTTP"
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.dashboard.arn
}

# Auto-scaling configuration (minimal for low traffic)
resource "aws_apprunner_auto_scaling_configuration_version" "dashboard" {

  auto_scaling_configuration_name = "sensing-garden-dashboard-scaling"
  
  max_concurrency = 10
  max_size        = 2
  min_size        = 1
}

# Output the service URL
output "dashboard_url" {
  value = aws_apprunner_service.dashboard.service_url
  description = "URL of the dashboard service"
}
