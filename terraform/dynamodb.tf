resource "aws_dynamodb_table" "sensor_detections" {
  name         = "sensor_detections"
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
    name               = "model_id_index"
    hash_key           = "model_id"
    projection_type    = "ALL"
  }
}

# Table for storing classification results
resource "aws_dynamodb_table" "sensor_classifications" {
  name         = "sensor_classifications"
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
}

# Table for storing model information
resource "aws_dynamodb_table" "models" {
  name         = "models"
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
    name               = "type_index"
    hash_key           = "type"
    projection_type    = "ALL"
  }
}