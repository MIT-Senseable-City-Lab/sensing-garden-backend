variable "deployments_api_key_value" {
  description = "Pre-generated API key value for the deployments dashboard integration"
  type        = string
  sensitive   = true
}

variable "setup_code" {
  description = "Shared setup code for device self-registration"
  type        = string
  sensitive   = true
}
