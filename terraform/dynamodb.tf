# Create detections table
resource "aws_dynamodb_table" "sensor_detections" {
  name         = "sensing-garden-detections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "model_id"
    type = "S"
  }

  attribute {
    name = "bounding_box"
    type = "S"
  }

  global_secondary_index {
    name               = "model_id_index"
    hash_key           = "model_id"
    projection_type    = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = all
  }
}

# Create classifications table
resource "aws_dynamodb_table" "sensor_classifications" {
  name         = "sensing-garden-classifications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "model_id"
    type = "S"
  }

  attribute {
    name = "species"
    type = "S"
  }

  attribute {
    name = "bounding_box"
    type = "S"
  }

  global_secondary_index {
    name               = "model_id_index"
    hash_key           = "model_id"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "species_index"
    hash_key           = "species"
    projection_type    = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = all
  }
}

# Create models table
resource "aws_dynamodb_table" "models" {
  name         = "sensing-garden-models"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  range_key    = "timestamp"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "type"
    type = "S"
  }

  attribute {
    name = "bounding_box"
    type = "S"
  }

  global_secondary_index {
    name               = "type_index"
    hash_key           = "type"
    projection_type    = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = all
  }
}

# Create videos table
resource "aws_dynamodb_table" "videos" {
  name         = "sensing-garden-videos"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "type"
    type = "S"
  }

  global_secondary_index {
    name               = "type_index"
    hash_key           = "type"
    projection_type    = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = all
    # This will prevent Terraform from trying to recreate the table if it already exists
    create_before_destroy = true
  }
}