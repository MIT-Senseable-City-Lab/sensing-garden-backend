resource "aws_quicksight_data_source" "dynamodb" {
  data_source_id   = "dynamodb-datasource"
  aws_account_id   = "${data.aws_caller_identity.current.account_id}"
  name             = "DynamoDBDataSource"
  type             = "DYNAMODB"
  data_source_parameters {
    dynamodb {
      table_name = aws_dynamodb_table.sensor_detections.name
    }
  }
}

resource "aws_quicksight_refresh_schedule" "auto_refresh" {
  data_set_id = aws_quicksight_data_source.dynamodb.data_source_id
  schedule_id = "auto-refresh"
  refresh_interval = "10 SECONDS"
}