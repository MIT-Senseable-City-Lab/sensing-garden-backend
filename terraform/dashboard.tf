# GitHub connection for App Runner
resource "aws_apprunner_connection" "github" {
  connection_name = "sensing-garden-github"
  provider_type   = "GITHUB"
  
  # This will create the connection, but you still need to manually authorize it
  # in the AWS Console before it can be used
  lifecycle {
    ignore_changes = [status]
  }
}

# App Runner service
resource "aws_apprunner_service" "dashboard" {

  service_name = "sensing-garden-dashboard"

  source_configuration {
    auto_deployments_enabled = true
    authentication_configuration {
      connection_arn = aws_apprunner_connection.github.arn
    }
    code_repository {
      source_directory = "dashboard"  # Specify the directory containing the Flask app
      code_configuration {
        code_configuration_values {
          build_command = "pip install poetry && poetry install"
          port         = "5052"  # Using the port that Flask runs on by default
          runtime      = "PYTHON_3"
          start_command = "cd dashboard && poetry run python -c \"import os; from app import app; app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5052)))\""
          runtime_environment_variables = {
            "API_URL" = aws_apigatewayv2_api.http_api.api_endpoint,
            "IMAGES_BUCKET" = "sensing-garden-images",
            "PYTHONPATH" = "/var/task/dashboard" # Ensure Python can find modules in the dashboard directory
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
