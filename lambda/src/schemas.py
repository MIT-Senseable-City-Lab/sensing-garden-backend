"""
Sensing Garden Data Schemas — Source of Truth

Each model corresponds to one DynamoDB table.
Used by the S3 trigger Lambda for validation on write,
and by the API Lambda for response serialization.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Track(BaseModel):
    track_id: str
    device_id: str
    timestamp: str
    model_id: str
    family: str
    genus: str
    species: str
    family_confidence: float = Field(ge=0, le=1)
    genus_confidence: float = Field(ge=0, le=1)
    species_confidence: float = Field(ge=0, le=1)
    num_detections: int
    s3_prefix: str
    composite_key: Optional[str] = None
    deployment_id: Optional[str] = None


class Classification(BaseModel):
    device_id: str
    timestamp: str
    track_id: str
    model_id: str
    image_key: str
    image_bucket: str
    family: str
    genus: str
    species: str
    family_confidence: float = Field(ge=0, le=1)
    genus_confidence: float = Field(ge=0, le=1)
    species_confidence: float = Field(ge=0, le=1)
    frame_number: int
    bounding_box: list[float]


class Device(BaseModel):
    device_id: str
    parent_device_id: Optional[str] = None
    created: Optional[str] = None


class DeviceApiKey(BaseModel):
    device_id: str
    api_key: str
    dot_ids: Optional[list[str]] = None
    created: str
    status: str


class MLModel(BaseModel):
    id: str
    timestamp: str
    name: Optional[str] = None
    description: Optional[str] = None
    model_type: Optional[str] = None
    s3_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    labels_key: Optional[str] = None
    sha256: Optional[str] = None


class Heartbeat(BaseModel):
    device_id: str
    timestamp: str
    cpu_temperature_celsius: Optional[float] = None
    storage_free_bytes: Optional[int] = None
    storage_total_bytes: Optional[int] = None
    uptime_seconds: Optional[float] = None
    dot_status: Optional[list[dict]] = None


class Deployment(BaseModel):
    deployment_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    model_id: Optional[str] = None
    location: Optional[dict] = None
    image_key: Optional[str] = None
    image_bucket: Optional[str] = None


class DeploymentDeviceConnection(BaseModel):
    deployment_id: str
    device_id: str
    location: Optional[dict] = None
    added_at: Optional[str] = None


class EnvironmentalReading(BaseModel):
    device_id: str
    timestamp: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pm1p0: Optional[float] = None
    pm2p5: Optional[float] = None
    pm4p0: Optional[float] = None
    pm10p0: Optional[float] = None
    voc_index: Optional[float] = None
    nox_index: Optional[float] = None
    light_level: Optional[float] = None
    pressure: Optional[float] = None
    location: Optional[dict] = None


class Video(BaseModel):
    device_id: str
    timestamp: str
    video_key: str
    video_bucket: str
    s3_prefix: Optional[str] = None
    fps: Optional[float] = None
    total_frames: Optional[int] = None
    duration_seconds: Optional[float] = None
