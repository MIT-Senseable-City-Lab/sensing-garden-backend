# =============================================================================
# Variables
# =============================================================================

variable "dashboard_password" {
  type        = string
  sensitive   = true
  description = "Login password for the sensing garden dashboard"
}

variable "dashboard_secret_key" {
  type        = string
  sensitive   = true
  description = "Flask session secret key for the dashboard"
}

# =============================================================================
# S3 Bucket for Deployment Artifacts
# =============================================================================

resource "aws_s3_bucket" "web_deploy" {
  bucket = "scl-sensing-garden-web-deploy"
}

resource "aws_s3_bucket_public_access_block" "web_deploy" {
  bucket = aws_s3_bucket.web_deploy.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# IAM Role + Instance Profile for EB EC2 Instances
# =============================================================================

resource "aws_iam_role" "eb_ec2_role" {
  name = "eb-sensing-garden-web-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eb_web_tier" {
  role       = aws_iam_role.eb_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier"
}

resource "aws_iam_role_policy" "eb_deploy_bucket_access" {
  name = "eb-sensing-garden-web-deploy-bucket"
  role = aws_iam_role.eb_ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.web_deploy.arn,
          "${aws_s3_bucket.web_deploy.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "eb_s3_access" {
  name = "eb-sensing-garden-web-s3-policy"
  role = aws_iam_role.eb_ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.models.arn,
          "${aws_s3_bucket.models.arn}/*",
          aws_s3_bucket.sensor_videos.arn,
          "${aws_s3_bucket.sensor_videos.arn}/*",
          aws_s3_bucket.sensor_images.arn,
          "${aws_s3_bucket.sensor_images.arn}/*",
          aws_s3_bucket.output.arn,
          "${aws_s3_bucket.output.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "eb_ec2_profile" {
  name = "eb-sensing-garden-web-profile"
  role = aws_iam_role.eb_ec2_role.name
}

# =============================================================================
# EB Service Role
# =============================================================================

resource "aws_iam_role" "eb_service_role" {
  name = "eb-sensing-garden-web-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "elasticbeanstalk.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eb_enhanced_health" {
  role       = aws_iam_role.eb_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSElasticBeanstalkEnhancedHealth"
}

resource "aws_iam_role_policy_attachment" "eb_managed_updates" {
  role       = aws_iam_role.eb_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkManagedUpdatesCustomerRolePolicy"
}

# =============================================================================
# Elastic Beanstalk Application
# =============================================================================

resource "aws_elastic_beanstalk_application" "web" {
  name = "sensing-garden-web"
}

# =============================================================================
# Elastic Beanstalk Environment
# =============================================================================

resource "aws_elastic_beanstalk_environment" "web" {
  name                = "sensing-garden-web-prod"
  application         = aws_elastic_beanstalk_application.web.name
  solution_stack_name = "64bit Amazon Linux 2023 v4.12.0 running Python 3.11"

  setting {
    namespace = "aws:elasticbeanstalk:environment"
    name      = "EnvironmentType"
    value     = "SingleInstance"
  }

  setting {
    namespace = "aws:elasticbeanstalk:environment"
    name      = "ServiceRole"
    value     = aws_iam_role.eb_service_role.arn
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "InstanceType"
    value     = "t3.micro"
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "IamInstanceProfile"
    value     = aws_iam_instance_profile.eb_ec2_profile.name
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "FLASK_SECRET_KEY"
    value     = var.dashboard_secret_key
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "SENSING_GARDEN_API_KEY"
    value     = aws_api_gateway_api_key.frontend_key.value
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "DASHBOARD_PASSWORD"
    value     = var.dashboard_password
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "API_BASE_URL"
    value     = "https://api.sensinggarden.com/v1"
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "WEB_READ_ONLY"
    value     = "false"
  }
}

# =============================================================================
# Outputs
# =============================================================================

output "dashboard_url" {
  value = aws_elastic_beanstalk_environment.web.cname
}
