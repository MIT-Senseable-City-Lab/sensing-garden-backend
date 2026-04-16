from __future__ import annotations

from io import BytesIO
import re
from enum import Enum
from typing import Any, Iterable, List, Optional, Protocol, Tuple

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field


class CompositeSource(str, Enum):
    FLICK = "flick"
    DOT = "dot"

    @classmethod
    def from_results_key(cls, results_key: str) -> "CompositeSource":
        prefix_leaf = derive_s3_prefix(results_key).rsplit("/", 1)[-1]
        return cls.DOT if re.fullmatch(r"\d{8}", prefix_leaf) else cls.FLICK

    def crop_prefix(self, s3_prefix: str, track: dict[str, Any]) -> str:
        track_id = str(track["track_id"])
        if self is CompositeSource.DOT:
            return f"{s3_prefix}/crops/{track_id}_{track['timestamp']}"
        return f"{s3_prefix}/crops/{track_id[:8]}"

    def label_key(self, s3_prefix: str, track: dict[str, Any]) -> str:
        return f"{s3_prefix}/labels/{track['track_id']}.json"

    def composite_keys(self, s3_prefix: str, track: dict[str, Any]) -> list[str]:
        track_id = str(track["track_id"])
        short_id = track_id[:8]
        if self is CompositeSource.DOT:
            return [f"{s3_prefix}/composites/{track_id}_{track['timestamp']}.jpg"]
        return [f"{s3_prefix}/composites/track_{short_id}.jpg"]


class CompositeStatus(str, Enum):
    CREATED = "created"
    SKIPPED = "skipped"


class CompositeSkipReason(str, Enum):
    EXISTS = "exists"
    NO_BOXES = "no_boxes"
    MISSING_CROPS = "missing_crops"
    MISSING_DOT_LABEL = "missing_dot_label"
    INVALID_DOT_LABEL = "invalid_dot_label"
    CROP_LABEL_MISMATCH = "crop_label_mismatch"


class CropPlacement(BaseModel):
    crop_key: str
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    x2: int = Field(gt=0)
    y2: int = Field(gt=0)


class CompositePlan(BaseModel):
    source: CompositeSource
    composite_key: str
    canvas_width: int = Field(gt=0)
    canvas_height: int = Field(gt=0)
    placements: list[CropPlacement]


class CompositeResult(BaseModel):
    status: CompositeStatus
    source: CompositeSource
    composite_key: str
    placements: int = 0
    reason: Optional[CompositeSkipReason] = None


class CompositeStorage(Protocol):
    def read_json(self, bucket: str, key: str) -> dict[str, Any]:
        ...

    def read_bytes(self, bucket: str, key: str) -> bytes:
        ...

    def write_bytes(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        ...

    def exists(self, bucket: str, key: str) -> bool:
        ...

    def list_keys(self, bucket: str, prefix: str, suffix: str = "") -> list[str]:
        ...


def derive_s3_prefix(results_key: str) -> str:
    return results_key.rsplit("/results.json", 1)[0]


def iter_result_tracks(results: dict[str, Any]) -> Iterable[dict[str, Any]]:
    tracks = results.get("tracks", [])
    explicit = [track for track in tracks if track.get("confirmed") is True or track.get("is_confirmed") is True]
    return explicit or tracks


def candidate_composite_keys(s3_prefix: str, track: dict[str, Any]) -> list[str]:
    return CompositeSource.from_results_key(f"{s3_prefix}/results.json").composite_keys(s3_prefix, track)


def ensure_results_composites(storage: CompositeStorage, bucket: str, results_key: str) -> list[CompositeResult]:
    results = storage.read_json(bucket, results_key)
    return [
        ensure_track_composite(storage, bucket, results_key, track)
        for track in iter_result_tracks(results)
    ]


def ensure_track_composite(
    storage: CompositeStorage,
    bucket: str,
    results_key: str,
    track: dict[str, Any],
) -> CompositeResult:
    source = CompositeSource.from_results_key(results_key)
    prefix = derive_s3_prefix(results_key)
    composite_key = source.composite_keys(prefix, track)[0]
    if storage.exists(bucket, composite_key):
        return _skipped(source, composite_key, CompositeSkipReason.EXISTS)

    plan = _build_plan(storage, bucket, prefix, source, track, composite_key)
    if isinstance(plan, CompositeResult):
        return plan

    image_bytes = _render_composite(storage, bucket, plan)
    storage.write_bytes(bucket, composite_key, image_bytes, "image/jpeg")
    return CompositeResult(
        status=CompositeStatus.CREATED,
        source=source,
        composite_key=composite_key,
        placements=len(plan.placements),
    )


def _build_plan(
    storage: CompositeStorage,
    bucket: str,
    prefix: str,
    source: CompositeSource,
    track: dict[str, Any],
    composite_key: str,
) -> CompositePlan | CompositeResult:
    if source is CompositeSource.DOT:
        return _build_dot_plan(storage, bucket, prefix, source, track, composite_key)
    return _build_flick_plan(storage, bucket, prefix, source, track, composite_key)


def _build_flick_plan(
    storage: CompositeStorage,
    bucket: str,
    prefix: str,
    source: CompositeSource,
    track: dict[str, Any],
    composite_key: str,
) -> CompositePlan | CompositeResult:
    boxes = [_flick_placement(prefix, track, frame) for frame in track.get("frames", []) if frame.get("bbox")]
    placements = [placement for placement in boxes if placement is not None]
    if not placements:
        return _skipped(source, composite_key, CompositeSkipReason.NO_BOXES)
    if any(not storage.exists(bucket, placement.crop_key) for placement in placements):
        return _skipped(source, composite_key, CompositeSkipReason.MISSING_CROPS)
    return CompositePlan(
        source=source,
        composite_key=composite_key,
        canvas_width=max(placement.x2 for placement in placements),
        canvas_height=max(placement.y2 for placement in placements),
        placements=placements,
    )


def _flick_placement(prefix: str, track: dict[str, Any], frame: dict[str, Any]) -> Optional[CropPlacement]:
    bbox = frame["bbox"]
    x1, y1, x2, y2 = [int(value) for value in bbox]
    if x2 <= x1 or y2 <= y1:
        return None
    frame_number = int(frame["frame_number"])
    short_id = str(track["track_id"])[:8]
    return CropPlacement(
        crop_key=f"{prefix}/crops/{short_id}/frame_{frame_number:06d}.jpg",
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def _build_dot_plan(
    storage: CompositeStorage,
    bucket: str,
    prefix: str,
    source: CompositeSource,
    track: dict[str, Any],
    composite_key: str,
) -> CompositePlan | CompositeResult:
    label_key = source.label_key(prefix, track)
    if not storage.exists(bucket, label_key):
        return _skipped(source, composite_key, CompositeSkipReason.MISSING_DOT_LABEL)

    crop_keys = storage.list_keys(bucket, source.crop_prefix(prefix, track), suffix=".jpg")
    if not crop_keys:
        return _skipped(source, composite_key, CompositeSkipReason.MISSING_CROPS)

    labels = storage.read_json(bucket, label_key)
    plan = _dot_plan_from_points(source, composite_key, labels, crop_keys)
    if plan is not None:
        return plan
    plan = _dot_plan_from_frames(source, composite_key, labels, crop_keys)
    if plan is not None:
        return plan
    return _skipped(source, composite_key, CompositeSkipReason.INVALID_DOT_LABEL)


def _dot_plan_from_points(
    source: CompositeSource,
    composite_key: str,
    labels: dict[str, Any],
    crop_keys: list[str],
) -> Optional[CompositePlan | CompositeResult]:
    resolution = labels.get("resolution")
    points = labels.get("points")
    if points is None:
        return None
    if not _valid_dot_points(resolution, points):
        return _skipped(source, composite_key, CompositeSkipReason.INVALID_DOT_LABEL)
    if len(crop_keys) != len(points):
        return _skipped(source, composite_key, CompositeSkipReason.CROP_LABEL_MISMATCH)

    width = int(resolution["width"])
    height = int(resolution["height"])
    placements = [
        _dot_placement(crop_key, point, width, height)
        for crop_key, point in zip(crop_keys, _sorted_dot_points(points))
    ]
    placements = [placement for placement in placements if placement is not None]
    if not placements:
        return _skipped(source, composite_key, CompositeSkipReason.NO_BOXES)
    return CompositePlan(
        source=source,
        composite_key=composite_key,
        canvas_width=width,
        canvas_height=height,
        placements=placements,
    )


def _dot_plan_from_frames(
    source: CompositeSource,
    composite_key: str,
    labels: dict[str, Any],
    crop_keys: list[str],
) -> Optional[CompositePlan | CompositeResult]:
    frames = labels.get("frames")
    if frames is None:
        return None
    if not _valid_dot_frames(frames):
        return _skipped(source, composite_key, CompositeSkipReason.INVALID_DOT_LABEL)
    if len(crop_keys) != len(frames):
        return _skipped(source, composite_key, CompositeSkipReason.CROP_LABEL_MISMATCH)

    placements = [_dot_frame_placement(crop_key, frame) for crop_key, frame in zip(crop_keys, _sorted_dot_frames(frames))]
    width = max(placement.x2 for placement in placements)
    height = max(placement.y2 for placement in placements)
    return CompositePlan(
        source=source,
        composite_key=composite_key,
        canvas_width=width,
        canvas_height=height,
        placements=placements,
    )


def _valid_dot_points(resolution: Any, points: Any) -> bool:
    if not isinstance(resolution, dict) or not isinstance(points, list) or not points:
        return False
    try:
        width = int(resolution.get("width", 0))
        height = int(resolution.get("height", 0))
    except (TypeError, ValueError):
        return False
    return width > 0 and height > 0 and all(_valid_dot_point(point) for point in points)


def _valid_dot_point(point: Any) -> bool:
    if not isinstance(point, dict):
        return False
    try:
        int(point["frameIndex"])
        int(point["x"])
        int(point["y"])
        return int(point["width"]) > 0 and int(point["height"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


def _valid_dot_frames(frames: Any) -> bool:
    return isinstance(frames, list) and bool(frames) and all(_valid_dot_frame(frame) for frame in frames)


def _valid_dot_frame(frame: Any) -> bool:
    if not isinstance(frame, dict):
        return False
    try:
        bbox = frame["bbox"]
        int(frame["frame_number"])
        return (
            len(bbox) == 4
            and int(bbox[0]) >= 0
            and int(bbox[1]) >= 0
            and int(bbox[2]) > 0
            and int(bbox[3]) > 0
        )
    except (KeyError, TypeError, ValueError):
        return False


def _sorted_dot_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(points, key=lambda point: int(point["frameIndex"]))


def _sorted_dot_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(frames, key=lambda frame: int(frame["frame_number"]))


def _dot_placement(crop_key: str, point: dict[str, Any], width: int, height: int) -> Optional[CropPlacement]:
    x1 = int(point["x"])
    y1 = int(point["y"])
    x2 = x1 + int(point["width"])
    y2 = y1 + int(point["height"])
    return _clipped_placement(crop_key, x1, y1, x2, y2, width, height)


def _dot_frame_placement(crop_key: str, frame: dict[str, Any]) -> CropPlacement:
    bbox = frame["bbox"]
    x1 = int(bbox[0])
    y1 = int(bbox[1])
    x2 = x1 + int(bbox[2])
    y2 = y1 + int(bbox[3])
    return CropPlacement(crop_key=crop_key, x1=x1, y1=y1, x2=x2, y2=y2)


def _clipped_placement(
    crop_key: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    width: int,
    height: int,
) -> Optional[CropPlacement]:
    clipped = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
        return None
    return CropPlacement(crop_key=crop_key, x1=clipped[0], y1=clipped[1], x2=clipped[2], y2=clipped[3])


def _render_composite(storage: CompositeStorage, bucket: str, plan: CompositePlan) -> bytes:
    image = Image.new("RGB", (plan.canvas_width, plan.canvas_height), "black")
    draw = ImageDraw.Draw(image)
    centers: list[Tuple[int, int]] = []
    for placement in plan.placements:
        crop = Image.open(BytesIO(storage.read_bytes(bucket, placement.crop_key))).convert("RGB")
        size = placement.x2 - placement.x1, placement.y2 - placement.y1
        image.paste(crop.resize(size), (placement.x1, placement.y1))
        draw.rectangle((placement.x1, placement.y1, placement.x2 - 1, placement.y2 - 1), outline="red", width=2)
        centers.append(((placement.x1 + placement.x2) // 2, (placement.y1 + placement.y2) // 2))

    if len(centers) > 1:
        draw.line(centers, fill="red", width=2)
    if centers:
        x, y = centers[0]
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="green")
    draw.text((10, 10), f"{len(plan.placements)} detections", fill="white")

    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _skipped(source: CompositeSource, composite_key: str, reason: CompositeSkipReason) -> CompositeResult:
    return CompositeResult(status=CompositeStatus.SKIPPED, source=source, composite_key=composite_key, reason=reason)
