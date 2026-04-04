# Create S3 bucket for images
resource "aws_s3_bucket" "sensor_images" {
  bucket = "scl-sensing-garden-images"

  lifecycle {
    prevent_destroy = true
  }
}

# Configure public access settings for images bucket
resource "aws_s3_bucket_public_access_block" "sensor_images" {
  bucket = aws_s3_bucket.sensor_images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Configure CORS for images bucket
resource "aws_s3_bucket_cors_configuration" "sensor_images" {
  bucket = aws_s3_bucket.sensor_images.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

# Create S3 bucket for videos
resource "aws_s3_bucket" "sensor_videos" {
  bucket = "scl-sensing-garden-videos"

  lifecycle {
    prevent_destroy = true
  }
}

# Configure public access settings for videos bucket
resource "aws_s3_bucket_public_access_block" "sensor_videos" {
  bucket = aws_s3_bucket.sensor_videos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Configure CORS for videos bucket
resource "aws_s3_bucket_cors_configuration" "sensor_videos" {
  bucket = aws_s3_bucket.sensor_videos.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

# =============================================================================
# Models Bucket - Public read access for ML model downloads
# =============================================================================

# Create S3 bucket for ML models (public read)
resource "aws_s3_bucket" "models" {
  bucket = "scl-sensing-garden-models"

  lifecycle {
    prevent_destroy = true
  }
}

# Allow public access for models bucket (needed for public downloads)
resource "aws_s3_bucket_public_access_block" "models" {
  bucket = aws_s3_bucket.models.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# Bucket policy to allow public read access
resource "aws_s3_bucket_policy" "models_public_read" {
  bucket = aws_s3_bucket.models.id

  # Ensure public access block is configured first
  depends_on = [aws_s3_bucket_public_access_block.models]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicListBucket"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.models.arn
      },
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.models.arn}/*"
      }
    ]
  })
}

# Configure CORS for models bucket
resource "aws_s3_bucket_cors_configuration" "models" {
  bucket = aws_s3_bucket.models.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}

# =============================================================================
# Output Bucket - Private bucket for pipeline results
# =============================================================================

# Create S3 bucket for pipeline output
resource "aws_s3_bucket" "output" {
  bucket = "scl-sensing-garden"
}

# Configure public access settings for output bucket (private)
resource "aws_s3_bucket_public_access_block" "output" {
  bucket = aws_s3_bucket.output.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Configure CORS for output bucket
resource "aws_s3_bucket_cors_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}
