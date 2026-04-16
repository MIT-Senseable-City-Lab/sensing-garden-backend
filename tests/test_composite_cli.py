from __future__ import annotations

from io import BytesIO
import json
import sys
from pathlib import Path

from PIL import Image
from pytest import CaptureFixture


TRIGGER_SRC = Path(__file__).resolve().parents[1] / "trigger" / "src"
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)
sys.path.insert(0, str(TRIGGER_SRC))

import composite_cli  # noqa: E402

sys.path.remove(str(TRIGGER_SRC))
sys.modules.pop("activity", None)
sys.modules.pop("schemas", None)
sys.modules.pop("trigger_handler", None)


def _write_json(root: Path, key: str, payload: dict[str, object]) -> None:
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jpeg(root: Path, key: str, color: str) -> None:
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (10, 10), color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    path.write_bytes(buffer.getvalue())


def _assert_near_color(image: Image.Image, xy: tuple[int, int], expected: tuple[int, int, int]) -> None:
    actual = image.getpixel(xy)
    assert isinstance(actual, tuple)
    assert all(abs(channel - target) < 35 for channel, target in zip(actual[:3], expected))


def _track(track_id: str, timestamp: str, frames: list[dict[str, object]]) -> dict[str, object]:
    return {
        "track_id": track_id,
        "timestamp": timestamp,
        "final_prediction": {
            "family": "Family",
            "genus": "Genus",
            "species": "Species",
            "family_confidence": 0.9,
            "genus_confidence": 0.8,
            "species_confidence": 0.7,
        },
        "num_detections": len(frames),
        "frames": frames,
    }


def test_cli_generates_dot_composite_from_points_and_crops(tmp_path: Path) -> None:
    results_key = "v1/FLIK2-dot01/20260412/results.json"
    _write_json(
        tmp_path,
        results_key,
        {"source_device": "FLIK2-dot01", "date": "20260412", "tracks": [_track("12224", "163315", [])]},
    )
    _write_json(
        tmp_path,
        "v1/FLIK2-dot01/20260412/labels/12224.json",
        {
            "resolution": {"width": 100, "height": 80},
            "points": [
                {"x": 10, "y": 20, "width": 10, "height": 10, "frameIndex": 1505},
                {"x": 30, "y": 25, "width": 10, "height": 10, "frameIndex": 1506},
            ],
        },
    )
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000000.jpg", "white")
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000001.jpg", "white")

    exit_code = composite_cli.main(
        [
            "--bucket",
            "bucket",
            "--local-root",
            str(tmp_path),
            "generate",
            "--results-key",
            results_key,
        ]
    )

    composite_path = tmp_path / "v1/FLIK2-dot01/20260412/composites/12224_163315.jpg"
    assert exit_code == 0
    assert composite_path.exists()
    assert Image.open(composite_path).size == (100, 80)


def test_cli_pairs_dot_crops_with_frame_index_order(tmp_path: Path) -> None:
    results_key = "v1/FLIK2-dot01/20260412/results.json"
    _write_json(
        tmp_path,
        results_key,
        {"source_device": "FLIK2-dot01", "date": "20260412", "tracks": [_track("12224", "163315", [])]},
    )
    _write_json(
        tmp_path,
        "v1/FLIK2-dot01/20260412/labels/12224.json",
        {
            "resolution": {"width": 100, "height": 80},
            "points": [
                {"x": 60, "y": 50, "width": 20, "height": 20, "frameIndex": 1506},
                {"x": 10, "y": 10, "width": 20, "height": 20, "frameIndex": 1505},
            ],
        },
    )
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000000.jpg", "white")
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000001.jpg", "blue")

    exit_code = composite_cli.main(
        [
            "--bucket",
            "bucket",
            "--local-root",
            str(tmp_path),
            "generate",
            "--results-key",
            results_key,
        ]
    )

    composite = Image.open(tmp_path / "v1/FLIK2-dot01/20260412/composites/12224_163315.jpg")
    assert exit_code == 0
    _assert_near_color(composite, (15, 25), (255, 255, 255))
    _assert_near_color(composite, (65, 65), (0, 0, 255))


def test_cli_generates_dot_composite_from_frame_bboxes(tmp_path: Path) -> None:
    results_key = "v1/FLIK2-dot01/20260413/results.json"
    _write_json(
        tmp_path,
        results_key,
        {"source_device": "FLIK2-dot01", "date": "20260413", "tracks": [_track("157868", "184852", [])]},
    )
    _write_json(
        tmp_path,
        "v1/FLIK2-dot01/20260413/labels/157868.json",
        {
            "frames": [
                {"frame_number": 1616872, "bbox": [60, 50, 20, 20]},
                {"frame_number": 1616870, "bbox": [10, 10, 20, 20]},
            ],
        },
    )
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260413/crops/157868_184852/frame_000000.jpg", "white")
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260413/crops/157868_184852/frame_000001.jpg", "blue")

    exit_code = composite_cli.main(
        [
            "--bucket",
            "bucket",
            "--local-root",
            str(tmp_path),
            "generate",
            "--results-key",
            results_key,
        ]
    )

    composite = Image.open(tmp_path / "v1/FLIK2-dot01/20260413/composites/157868_184852.jpg")
    assert exit_code == 0
    assert composite.size == (80, 70)
    _assert_near_color(composite, (15, 25), (255, 255, 255))
    _assert_near_color(composite, (65, 65), (0, 0, 255))


def test_cli_generates_flick_composite_from_result_frames(tmp_path: Path) -> None:
    track_id = "bac42593-3d8c-443a-b114-11eb40051fc9"
    results_key = "v1/FLIK2/20260411_144804_275767/results.json"
    _write_json(
        tmp_path,
        results_key,
        {
            "source_device": "FLIK2",
            "date": "20260411",
            "tracks": [
                _track(
                    track_id,
                    "144804",
                    [
                        {"frame_number": 225, "bbox": [10, 20, 30, 40]},
                        {"frame_number": 228, "bbox": [40, 5, 50, 15]},
                    ],
                )
            ],
        },
    )
    _write_jpeg(tmp_path, "v1/FLIK2/20260411_144804_275767/crops/bac42593/frame_000225.jpg", "white")
    _write_jpeg(tmp_path, "v1/FLIK2/20260411_144804_275767/crops/bac42593/frame_000228.jpg", "white")

    exit_code = composite_cli.main(
        [
            "--bucket",
            "bucket",
            "--local-root",
            str(tmp_path),
            "generate",
            "--results-key",
            results_key,
        ]
    )

    composite_path = tmp_path / "v1/FLIK2/20260411_144804_275767/composites/track_bac42593.jpg"
    assert exit_code == 0
    assert composite_path.exists()
    assert Image.open(composite_path).size == (50, 40)


def test_cli_backfills_nested_results(tmp_path: Path) -> None:
    results_key = "v1/FLIK2-dot01/20260412/results.json"
    _write_json(
        tmp_path,
        results_key,
        {"source_device": "FLIK2-dot01", "date": "20260412", "tracks": [_track("12224", "163315", [])]},
    )
    _write_json(
        tmp_path,
        "v1/FLIK2-dot01/20260412/labels/12224.json",
        {
            "resolution": {"width": 100, "height": 80},
            "points": [{"x": 10, "y": 20, "width": 10, "height": 10, "frameIndex": 1505}],
        },
    )
    _write_jpeg(tmp_path, "v1/FLIK2-dot01/20260412/crops/12224_163315/frame_000000.jpg", "white")

    exit_code = composite_cli.main(
        [
            "--bucket",
            "bucket",
            "--local-root",
            str(tmp_path),
            "backfill",
            "--prefix",
            "v1/FLIK2-dot01/",
        ]
    )

    composite_path = tmp_path / "v1/FLIK2-dot01/20260412/composites/12224_163315.jpg"
    assert exit_code == 0
    assert composite_path.exists()


def test_cli_skips_existing_composite(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    results_key = "v1/FLIK2-dot01/20260412/results.json"
    composite_key = "v1/FLIK2-dot01/20260412/composites/12224_163315.jpg"
    _write_json(
        tmp_path,
        results_key,
        {"source_device": "FLIK2-dot01", "date": "20260412", "tracks": [_track("12224", "163315", [])]},
    )
    _write_jpeg(tmp_path, composite_key, "white")

    exit_code = composite_cli.main(
        [
            "--bucket",
            "bucket",
            "--local-root",
            str(tmp_path),
            "generate",
            "--results-key",
            results_key,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload[0]["status"] == "skipped"
    assert payload[0]["reason"] == "exists"
