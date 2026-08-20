# sensing-garden-detections: DEAD TABLE, staged for removal (see
# Internal planning/reports/07-legacy-and-cleanup.md §C -- nothing has written to
# this table since the trigger moved to tracks + classifications).
#
# BEFORE APPLYING ANY OF THIS: back it up.
#   scripts/backup_table_cli.sh --table sensing-garden-detections --bucket scl-sensing-garden
# Writes gzip NDJSON to s3://scl-sensing-garden/backups/dynamodb/, deliberately
# outside the v1/v2 prefixes the trigger watches.
#
# APPLY IN TWO PASSES:
#   1. Apply this commit as-is (prevent_destroy already off below) to confirm
#      Terraform is willing to touch the resource without erroring.
#   2. Once confirmed, delete this resource block entirely (and its state entry
#      via `terraform apply` picking up the removal) in a follow-up commit.
# Do not delete the block in the same apply that first disables prevent_destroy --
# Terraform's plan for a resource being both unprotected and destroyed in one
# pass has caused surprises before; two passes keeps each step inspectable.
resource "aws_dynamodb_table" "sensor_detections" {
  name         = "sensing-garden-detections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"
  tags         = local.observation_detections_tags

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

  deletion_protection_enabled = false

  lifecycle {
    prevent_destroy = false
    ignore_changes = [
      read_capacity,
      write_capacity,
    ]
  }
}

# Create devices table
resource "aws_dynamodb_table" "devices" {
  name         = "sensing-garden-devices"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  tags         = local.device_registry_tags

  attribute {
    name = "device_id"
    type = "S"
  }


  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      deletion_protection_enabled,
      read_capacity,
      write_capacity,
    ]
  }
}

# Create classifications table
resource "aws_dynamodb_table" "sensor_classifications" {
  name         = "sensing-garden-classifications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"
  tags         = local.observation_classifications_tags

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # model_id, species, track_id are still written on every item -- they just no
  # longer back a GSI (model_id_index/species_index/track_id_index dropped below:
  # populated correctly but never queried by any route -- pure write-cost with no
  # read benefit, see the 2026-08 DB audit).

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      billing_mode,
      read_capacity,
      write_capacity,
    ]
  }
}

# Create models table
resource "aws_dynamodb_table" "models" {
  name         = "sensing-garden-models"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  range_key    = "timestamp"
  tags         = local.model_metadata_tags

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # type_index dropped: writer patches a constant "model" onto every row
  # (dynamodb.py store_model_data), so the index never had more than one
  # partition value and was never queried by IndexName anyway.

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      deletion_protection_enabled,
      read_capacity,
      write_capacity,
    ]
  }
}

# Create videos table
resource "aws_dynamodb_table" "videos" {
  name         = "sensing-garden-videos"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "timestamp"
  tags         = local.media_video_index_tags

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  # type_index dropped: the Video schema (schemas.py) has no `type` field and no
  # writer has ever stamped one -- this index has been empty since the table's
  # inception, and nothing queried it by IndexName either.

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      deletion_protection_enabled,
      read_capacity,
      write_capacity,
    ]
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
  tags         = local.observation_environment_tags

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
    ignore_changes = [
      read_capacity,
      write_capacity,
    ]
  }
}

# Create deployments table
resource "aws_dynamodb_table" "deployments" {
  name         = "sensing-garden-deployments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "deployment_id"
  tags         = local.deployment_registry_tags

  attribute {
    name = "deployment_id"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      read_capacity,
      write_capacity,
    ]
  }
}

# Create deployment-device-connections table
resource "aws_dynamodb_table" "deployment_device_connections" {
  name         = "sensing-garden-deployment-device-connections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "deployment_id"
  range_key    = "device_id"
  tags         = local.deployment_registry_tags

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
    ignore_changes = [
      read_capacity,
      write_capacity,
    ]
  }
}

# Create tracks table
resource "aws_dynamodb_table" "tracks" {
  name         = "sensing-garden-tracks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "track_id"
  range_key    = "device_id"
  tags         = local.observation_tracks_tags

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
  tags         = local.device_heartbeats_tags

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
  tags         = local.device_auth_tags

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

resource "aws_dynamodb_table" "activity_events" {
  name         = "sensing-garden-activity-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_date"
  range_key    = "timestamp_event_id"
  tags         = local.dashboard_audit_tags

  attribute {
    name = "event_date"
    type = "S"
  }

  attribute {
    name = "timestamp_event_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_dynamodb_table" "processed_objects" {
  name         = "sensing-garden-s3-processed-objects"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "object_id"
  tags         = local.pipeline_dedupe_tags

  attribute {
    name = "object_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  deletion_protection_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}
