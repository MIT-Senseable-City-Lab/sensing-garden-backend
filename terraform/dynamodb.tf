locals {
  db_schema = jsondecode(file("../common/db-schema.json"))
}

resource "aws_dynamodb_table" "sensor_detections" {
  name         = "sensor_detections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"

  dynamic "attribute" {
    for_each = local.db_schema.properties.sensor_detections.properties
    content {
      name = attribute.key
      type = attribute.value.type == "string" ? "S" : "N"
    }
  }

  global_secondary_index {
    name               = "model_id_index"
    hash_key           = "model_id"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "image_key_index"
    hash_key           = "image_key"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "image_bucket_index"
    hash_key           = "image_bucket"
    projection_type    = "ALL"
  }
}

# Table for storing classification results
resource "aws_dynamodb_table" "sensor_classifications" {
  name         = "sensor_classifications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"

  dynamic "attribute" {
    for_each = local.db_schema.properties.sensor_classifications.properties
    content {
      name = attribute.key
      type = attribute.value.type == "string" ? "S" : "N"
    }
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

  global_secondary_index {
    name               = "image_key_index"
    hash_key           = "image_key"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "family_index"
    hash_key           = "family"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "genus_index"
    hash_key           = "genus"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "family_confidence_index"
    hash_key           = "family_confidence"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "genus_confidence_index"
    hash_key           = "genus_confidence"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "species_confidence_index"
    hash_key           = "species_confidence"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "image_bucket_index"
    hash_key           = "image_bucket"
    projection_type    = "ALL"
  }
}

# Table for storing model information
resource "aws_dynamodb_table" "models" {
  name         = "models"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  range_key    = "timestamp"

  dynamic "attribute" {
    for_each = local.db_schema.properties.models.properties
    content {
      name = attribute.key
      type = attribute.value.type == "string" ? "S" : "N"
    }
  }

  global_secondary_index {
    name               = "type_index"
    hash_key           = "type"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "version_index"
    hash_key           = "version"
    projection_type    = "ALL"
  }

  global_secondary_index {
    name               = "description_index"
    hash_key           = "description"
    projection_type    = "ALL"
  }
}