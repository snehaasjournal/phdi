from phdi.containers.base_service import BaseService
from fastapi.testclient import TestClient
from app.config import get_settings
from pathlib import Path
from unittest.mock import patch
import pytest
from icecream import ic

app = BaseService(
    service_name="PHDI Orchestration",
    description_path=Path(__file__).parent.parent / "description.md",
).start()

get_settings()


@pytest.mark.asyncio
async def test_websocket_process_message_endpoint():
    client = TestClient(app)
    with open(
            Path(__file__).parent.parent.parent.parent
            / "tests"
            / "assets"
            / "orchestration"
            / "test_zip.zip",
            "rb",
    ) as file:
        test_zip = file
        ic(test_zip)
    with patch("app.services.call_apis") as mock_call_apis:
        with client.websocket_connect("/process-ws") as websocket:

            await websocket.send_bytes(test_zip)

    mock_call_apis.assert_called_with()



# @pytest.mark.asyncio
# async def test_process_message_endpoint_ws():
#     client = TestClient(app)
#     url = "ws://testserver/process-ws"
#
#     with patch("path.to.your.call_apis") as mock_call_apis:
#         async with client.websocket_connect(url) as websocket:
#             # Sending some sample data
#             sample_zipped_file = create_sample_zipped_file()  # Replace with a function that returns a sample zipped file as bytes
#             await websocket.send_bytes(sample_zipped_file)
#
#             # Additional logic to ensure that WebSocket messages are received and processed
#             # ...
#
#             # Assert that call_apis was called
#             mock_call_apis.assert_called()