from pathlib import Path

from trigger_handler import CollectingWriter, LocalStorageAdapter, process_results_object


FAKE_OUTPUT_ROOT = Path("/Users/deniz/Downloads/fake-output")


def main() -> int:
    storage = LocalStorageAdapter(str(FAKE_OUTPUT_ROOT))
    writer = CollectingWriter()

    result_files = sorted(
        path.relative_to(FAKE_OUTPUT_ROOT).as_posix()
        for path in FAKE_OUTPUT_ROOT.rglob("results.json")
    )

    assert len(result_files) == 3, result_files

    summaries = {}
    for key in result_files:
        summaries[key] = process_results_object(storage, writer, "fake-output", key)

    assert summaries["flick01/20260204_100000/results.json"]["tracks"] == 2
    assert summaries["flick01/20260204_100100/results.json"]["tracks"] == 7
    assert summaries["dot01/20260204/results.json"]["tracks"] == 1
    assert any(
        item["track_id"] == "a1b2c3d4" and item["frame_number"] == 926 and item["bounding_box"] == [380.0, 535.0, 23.0, 37.0]
        for item in writer.classifications
    )
    assert any(item["video_key"].endswith("video.mp4") for item in writer.videos)
    assert not any(item["device_id"] == "dot01" and item.get("video_key", "").endswith(".mp4") for item in writer.videos)

    print("local parse ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
