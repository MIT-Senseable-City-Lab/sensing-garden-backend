locals {
  common_tags = {
    Project     = "sensing-garden"
    Environment = "prod"
    ManagedBy   = "terraform"
    Repository  = "sensing-garden-backend"
  }

  api_handler_tags = {
    CostDomain    = "api"
    CostComponent = "api-handler"
  }

  api_http_tags = {
    CostDomain    = "api"
    CostComponent = "http-api"
  }

  api_key_edge_tags = {
    CostDomain    = "api"
    CostComponent = "edge-client-auth"
  }

  api_key_test_tags = {
    CostDomain    = "api"
    CostComponent = "test-client-auth"
  }

  dashboard_api_auth_tags = {
    CostDomain    = "dashboard"
    CostComponent = "dashboard-api-auth"
  }

  dashboard_audit_tags = {
    CostDomain    = "dashboard"
    CostComponent = "audit-events"
  }

  dashboard_deploy_tags = {
    CostDomain    = "dashboard"
    CostComponent = "web-deploy"
  }

  dashboard_web_tags = {
    CostDomain    = "dashboard"
    CostComponent = "web-app"
  }

  deployment_registry_tags = {
    CostDomain    = "deployment-management"
    CostComponent = "deployments"
  }

  device_auth_tags = {
    CostDomain    = "fleet"
    CostComponent = "device-auth"
  }

  device_heartbeats_tags = {
    CostDomain    = "fleet"
    CostComponent = "heartbeats"
  }

  device_registry_tags = {
    CostDomain    = "fleet"
    CostComponent = "devices"
  }

  media_images_tags = {
    CostDomain    = "media"
    CostComponent = "images"
  }

  media_video_index_tags = {
    CostDomain    = "media"
    CostComponent = "video-index"
  }

  media_videos_tags = {
    CostDomain    = "media"
    CostComponent = "videos"
  }

  model_artifacts_tags = {
    CostDomain    = "models"
    CostComponent = "model-artifacts"
  }

  model_metadata_tags = {
    CostDomain    = "models"
    CostComponent = "model-metadata"
  }

  observation_classifications_tags = {
    CostDomain    = "observations"
    CostComponent = "classifications"
  }

  observation_detections_tags = {
    CostDomain    = "observations"
    CostComponent = "detections"
  }

  observation_environment_tags = {
    CostDomain    = "observations"
    CostComponent = "environmental-readings"
  }

  observation_tracks_tags = {
    CostDomain    = "observations"
    CostComponent = "tracks"
  }

  pipeline_dedupe_tags = {
    CostDomain    = "pipeline"
    CostComponent = "dedupe"
  }

  pipeline_output_tags = {
    CostDomain    = "pipeline"
    CostComponent = "pipeline-output"
  }

  pipeline_processor_tags = {
    CostDomain    = "pipeline"
    CostComponent = "output-processor"
  }

  platform_dns_tags = {
    CostDomain    = "platform"
    CostComponent = "dns"
  }
}
