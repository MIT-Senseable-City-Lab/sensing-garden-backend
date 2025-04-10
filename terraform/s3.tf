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
    allowed_methods = ["GET"]
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
