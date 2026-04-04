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

  global_secondary_index {
    name            = "model_id_index"
    hash_key        = "model_id"
    range_key       = null
    projection_type = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

# Create devices table
resource "aws_dynamodb_table" "devices" {
  name         = "sensing-garden-devices"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"

  attribute {
    name = "device_id"
    type = "S"
  }


  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
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
    name = "track_id"
    type = "S"
  }

  global_secondary_index {
    name            = "model_id_index"
    hash_key        = "model_id"
    range_key       = null
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "species_index"
    hash_key        = "species"
    range_key       = null
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "track_id_index"
    hash_key        = "track_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      billing_mode,
      read_capacity,
      write_capacity,
      tags,
    ]
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

  global_secondary_index {
    name            = "type_index"
    hash_key        = "type"
    range_key       = null
    projection_type = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
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
    name            = "type_index"
    hash_key        = "type"
    range_key       = null
    projection_type = "ALL"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
    # This will prevent Terraform from trying to recreate the table if it already exists
    create_before_destroy = true
  }
}

# Create environmental readings table
resource "aws_dynamodb_table" "environmental_readings" {
  name         = "sensing-garden-environmental-readings"
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

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

# Create deployments table
resource "aws_dynamodb_table" "deployments" {
  name         = "sensing-garden-deployments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "deployment_id"

  attribute {
    name = "deployment_id"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

# Create deployment-device-connections table
resource "aws_dynamodb_table" "deployment_device_connections" {
  name         = "sensing-garden-deployment-device-connections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "deployment_id"
  range_key    = "device_id"

  attribute {
    name = "deployment_id"
    type = "S"
  }

  attribute {
    name = "device_id"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

# Create tracks table
resource "aws_dynamodb_table" "tracks" {
  name         = "sensing-garden-tracks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "track_id"
  range_key    = "device_id"

  attribute {
    name = "track_id"
    type = "S"
  }

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  global_secondary_index {
    name            = "device_id_index"
    hash_key        = "device_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}

# Create heartbeats table
resource "aws_dynamodb_table" "heartbeats" {
  name         = "sensing-garden-heartbeats"
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

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_dynamodb_table" "device_api_keys" {
  name         = "sensing-garden-device-api-keys"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "api_key"
    type = "S"
  }

  global_secondary_index {
    name            = "api_key_index"
    hash_key        = "api_key"
    projection_type = "ALL"
  }

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}
