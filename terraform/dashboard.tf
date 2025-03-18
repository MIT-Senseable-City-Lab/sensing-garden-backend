

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

# GitHub connection for App Runner
resource "aws_apprunner_connection" "github" {
  provider = aws.us_east_1
  connection_name = "sensing-garden-github"
  provider_type   = "GITHUB"
}

# IAM role for App Runner connection to GitHub
resource "aws_iam_role" "app_runner_service" {
  name = "sensing-garden-dashboard-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "build.apprunner.amazonaws.com"
      }
    }]
  })
}

# App Runner service
resource "aws_apprunner_service" "dashboard" {
  provider = aws.us_east_1
  service_name = "sensing-garden-dashboard"

  source_configuration {
    auto_deployments_enabled = true
    authentication_configuration {
      connection_arn = aws_apprunner_connection.github.arn
    }
    code_repository {
      code_configuration {
        code_configuration_values {
          build_command = "pip install poetry && poetry install"
          port         = "8080"
          runtime      = "PYTHON_3"
          start_command = "poetry run python -c \"import os; from app import app; app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))\""
          runtime_environment_variables = {
            "API_URL" = aws_apigatewayv2_api.http_api.api_endpoint
          }
        }
        configuration_source = "API"
      }
      repository_url = "https://github.com/daydemir/sensing-garden-backend"
      source_code_version {
        type  = "BRANCH"
        value = "main"
      }
    }
  }

  instance_configuration {
    cpu = "1024"
    memory = "2048"
    instance_role_arn = aws_iam_role.app_runner_service.arn
  }

  health_check_configuration {
    path = "/"
    protocol = "HTTP"
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.dashboard.arn
}

# Auto-scaling configuration (minimal for low traffic)
resource "aws_apprunner_auto_scaling_configuration_version" "dashboard" {
  provider = aws.us_east_1
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
