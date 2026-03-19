import json

import handler


def test_handle_delete_model_requires_model_id():
    response = handler.handle_delete_model({"body": json.dumps({})})

    assert response["statusCode"] == 400
    assert "model_id is required" in response["body"]


def test_handle_delete_model_calls_dynamodb(monkeypatch):
    captured = {}

    def fake_delete_model(model_id):
        captured["model_id"] = model_id
        return {"statusCode": 200, "body": json.dumps({"message": "deleted"})}

    monkeypatch.setattr(handler.dynamodb, "delete_model", fake_delete_model)

    response = handler.handle_delete_model({"body": json.dumps({"model_id": "bundle-model"})})

    assert response["statusCode"] == 200
    assert captured["model_id"] == "bundle-model"
