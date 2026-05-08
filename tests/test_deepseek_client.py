import unittest
from unittest.mock import patch

from audrey_llm.deepseek_client import DeepSeekClient


class FakeResponse:
    def __init__(self, status_code=200, lines=None, text=""):
        self.status_code = status_code
        self._lines = lines or []
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self, decode_unicode=True):
        yield from self._lines


class DeepSeekClientTests(unittest.TestCase):
    @patch("audrey_llm.deepseek_client.requests.post")
    def test_stream_chat_parses_sse_tokens(self, mock_post):
        mock_post.return_value = FakeResponse(
            lines=[
                "data: {\"choices\": [{\"delta\": {\"content\": \"Halo\"}}]}",
                "data: {\"choices\": [{\"delta\": {\"content\": \" dunia\"}}]}",
                "data: [DONE]",
            ],
        )
        client = DeepSeekClient(api_key="token", base_url="https://api.deepseek.com")

        chunks = list(client.stream_chat([{"role": "user", "content": "hai"}], "deepseek-v4-flash"))

        self.assertEqual(chunks, ["Halo", " dunia"])
        mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
