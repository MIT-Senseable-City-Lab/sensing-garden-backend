# S3 bucket for storing sensor images
resource "aws_s3_bucket" "sensor_images" {
  bucket = "sensing-garden-images"

  # Don't fail if the bucket already exists
  lifecycle {
    prevent_destroy = true
    ignore_changes = all
    # Use existing bucket if it already exists
    create_before_destroy = false
  }
}

# Then configure its public access settings
resource "aws_s3_bucket_public_access_block" "sensor_images" {
  bucket = aws_s3_bucket.sensor_images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  depends_on = [aws_s3_bucket.sensor_images]
  
  # This is a critical configuration to make this work
  lifecycle {
    # Ignore all attributes to prevent Terraform from trying to read the current state
    ignore_changes = all
  }
}

# Finally configure CORS
resource "aws_s3_bucket_cors_configuration" "sensor_images" {
  bucket = aws_s3_bucket.sensor_images.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }

  depends_on = [aws_s3_bucket.sensor_images]
  
  # This is a critical configuration to make this work
  lifecycle {
    # Ignore all attributes to prevent Terraform from trying to read the current state
    ignore_changes = all
  }
}
