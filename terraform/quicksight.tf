# Get the current AWS account ID
data "aws_caller_identity" "current" {}

# QuickSight configuration is commented out due to validation errors
# The AWS provider may have changed or this configuration needs to be updated

# resource "aws_quicksight_data_source" "dynamodb" {
#   data_source_id   = "dynamodb-datasource"
#   aws_account_id   = data.aws_caller_identity.current.account_id
#   name             = "DynamoDBDataSource"
#   type             = "DYNAMODB"
#   
#   # The correct format for QuickSight data source parameters may have changed
#   # Refer to the latest AWS provider documentation for the correct syntax
#   # parameters {
#   #   dynamodb {
#   #     table_name = aws_dynamodb_table.sensor_detections.name
#   #   }
#   # }
# }
#
# resource "aws_quicksight_refresh_schedule" "auto_refresh" {
#   data_set_id = aws_quicksight_data_source.dynamodb.data_source_id
#   schedule_id = "auto-refresh"
#   refresh_interval = "10 SECONDS"
# }