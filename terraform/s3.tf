resource "aws_s3_bucket" "sensor_images" {
  bucket = "sensing-garden"
}

resource "aws_s3_bucket_public_access_block" "sensor_images" {
  bucket = aws_s3_bucket.sensor_images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "sensor_images" {
  bucket = aws_s3_bucket.sensor_images.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3000
  }
}

