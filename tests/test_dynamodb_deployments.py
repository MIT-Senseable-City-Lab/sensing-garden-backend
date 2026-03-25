from botocore.exceptions import ClientError

import dynamodb


class _FakeTable:
    def __init__(self, error):
        self._error = error

    def put_item(self, **kwargs):
        raise self._error


def test_store_deployment_data_conflict(monkeypatch):
    error = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "exists",
            }
        },
        "PutItem",
    )
    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable(error))

    response = dynamodb.store_deployment_data({"deployment_id": "dep-1", "name": "A"})

    assert response["statusCode"] == 409


def test_store_deployment_device_connection_conflict(monkeypatch):
    error = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "exists",
            }
        },
        "PutItem",
    )
    monkeypatch.setattr(dynamodb.dynamodb, "Table", lambda name: _FakeTable(error))

    response = dynamodb.store_deployment_device_connection_data({
        "deployment_id": "dep-1",
        "device_id": "device-1",
    })

    assert response["statusCode"] == 409
