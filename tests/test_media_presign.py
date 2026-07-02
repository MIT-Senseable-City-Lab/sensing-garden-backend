import os

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import pytest

import s3
from routes import tracks


@pytest.fixture
def recorded_presigns(monkeypatch):
    """Patches s3.generate_presigned_url and records (key, bucket) call args.

    tracks.py imports the same function by reference (`from s3 import _presign_media`
    -> `generate_presigned_url`), so patching the s3 module's global is sufficient for
    both call sites: the lookup happens inside s3.py at call time either way.
    """
    calls = []

    def fake(key, bucket=None, expiration=s3.PRESIGNED_URL_EXPIRY):
        calls.append((key, bucket))
        return f"https://example.invalid/{bucket}/{key}"

    monkeypatch.setattr(s3, "generate_presigned_url", fake)
    return calls


def test_add_presigned_urls_uses_archive_for_stamped_video_row(recorded_presigns):
    """An archived row's video_key is a path inside the tar, not a real object at
    video_bucket -- the presign target must be the archive, not the member path."""
    item = {
        "video_key": "v1/FLIK4/20260625_141636/video.mp4",
        "video_bucket": "scl-sensing-garden-videos",
        "archive_key": "v2/archives/FLIK4/20260625_150000.tar",
        "archive_bucket": "scl-sensing-garden",
        "video_offset": 512,
        "video_size": 1024,
    }

    result = s3._add_presigned_urls({"items": [item]})

    assert recorded_presigns == [("v2/archives/FLIK4/20260625_150000.tar", "scl-sensing-garden")]
    assert result["items"][0]["video_url"] == (
        "https://example.invalid/scl-sensing-garden/v2/archives/FLIK4/20260625_150000.tar"
    )
    # unchanged: the stamped offset/size were already passing through untouched
    assert result["items"][0]["video_offset"] == 512
    assert result["items"][0]["video_size"] == 1024


def test_add_presigned_urls_standalone_video_row_unchanged(recorded_presigns):
    """A row with no archive fields keeps presigning its own key/bucket, exactly as
    today -- this must not regress when the archived branch is added."""
    item = {
        "video_key": "v1/FLIK4/20260625_141636/video.mp4",
        "video_bucket": "scl-sensing-garden-videos",
    }

    result = s3._add_presigned_urls({"items": [item]})

    assert recorded_presigns == [("v1/FLIK4/20260625_141636/video.mp4", "scl-sensing-garden-videos")]
    assert result["items"][0]["video_url"] == (
        "https://example.invalid/scl-sensing-garden-videos/v1/FLIK4/20260625_141636/video.mp4"
    )


def test_add_presigned_urls_uses_archive_for_stamped_image_row(recorded_presigns):
    item = {
        "image_key": "v1/FLIK4/20260625_141636/crop_0.jpg",
        "image_bucket": "scl-sensing-garden-images",
        "archive_key": "v2/archives/FLIK4/20260625_150000.tar",
        "archive_bucket": "scl-sensing-garden",
        "image_offset": 2048,
        "image_size": 256,
    }

    result = s3._add_presigned_urls({"items": [item]})

    assert recorded_presigns == [("v2/archives/FLIK4/20260625_150000.tar", "scl-sensing-garden")]
    assert result["items"][0]["image_url"] == (
        "https://example.invalid/scl-sensing-garden/v2/archives/FLIK4/20260625_150000.tar"
    )


def test_add_composite_url_uses_archive_for_stamped_composite_row(recorded_presigns):
    """Composites have no composite_bucket field -- they default to OUTPUT_BUCKET --
    but an archived row must still win over that default, same as video/image."""
    item = {
        "composite_key": "v1/FLIK4/20260625_141636/composite_0.jpg",
        "archive_key": "v2/archives/FLIK4/20260625_150000.tar",
        "archive_bucket": "scl-sensing-garden",
        "composite_offset": 4096,
        "composite_size": 128,
    }

    result = tracks._add_composite_url(item)

    assert recorded_presigns == [("v2/archives/FLIK4/20260625_150000.tar", "scl-sensing-garden")]
    assert result["composite_url"] == (
        "https://example.invalid/scl-sensing-garden/v2/archives/FLIK4/20260625_150000.tar"
    )


def test_add_composite_url_standalone_row_still_defaults_to_output_bucket(recorded_presigns):
    item = {"composite_key": "tracks/abc123/composite.jpg"}

    result = tracks._add_composite_url(item)

    assert recorded_presigns == [("tracks/abc123/composite.jpg", s3.OUTPUT_BUCKET)]
    assert result["composite_url"] == (
        f"https://example.invalid/{s3.OUTPUT_BUCKET}/tracks/abc123/composite.jpg"
    )


def test_add_presigned_urls_presign_failure_returns_none_not_raise(monkeypatch):
    def raising(key, bucket=None, expiration=s3.PRESIGNED_URL_EXPIRY):
        raise RuntimeError("boto3 boom")

    # generate_presigned_url itself already catches and returns None (s3.py) --
    # this proves _presign_media doesn't need its own try/except on top of that.
    monkeypatch.setattr(s3.s3, "generate_presigned_url", raising)

    item = {
        "video_key": "v1/FLIK4/20260625_141636/video.mp4",
        "video_bucket": "scl-sensing-garden-videos",
        "archive_key": "v2/archives/FLIK4/20260625_150000.tar",
        "archive_bucket": "scl-sensing-garden",
    }

    result = s3._add_presigned_urls({"items": [item]})

    assert result["items"][0]["video_url"] is None
