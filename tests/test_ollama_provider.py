import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from summarizer.providers.ollama_provider import OllamaProvider


SUMMARY = {
    "titulo": "Biblioteca oferece oficinas", "resumo": "A biblioteca oferece oficinas gratuitas.",
    "pontos_principais": [], "pessoas": [], "locais": [], "datas": [],
}


class OllamaTimeoutTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"OLLAMA_TIMEOUT_SECONDS": "900"})
        env.start()
        self.addCleanup(env.stop)

    def test_default_timeout_is_passed_to_the_request_and_preserves_summary_contract(self):
        body = json.dumps({"message": {"content": json.dumps(SUMMARY)}}).encode()
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen", return_value=BytesIO(body)) as request:
            result = OllamaProvider(model="gemma3:4b").summarize("Notícia original")
        self.assertEqual(result, SUMMARY)
        self.assertEqual(request.call_args.kwargs["timeout"], 900)
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["model"], "gemma3:4b")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"], {"temperature": 0})

    def test_environment_timeout_is_used_and_explicit_timeout_can_override_it(self):
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT_SECONDS": "1200"}):
            self.assertEqual(OllamaProvider().timeout, 1200)
            self.assertEqual(OllamaProvider(timeout=30).timeout, 30)

    def test_invalid_environment_timeout_reports_configuration_error(self):
        for value in ("0", "-1", "invalid", "nan", "inf", ""):
            with self.subTest(value=value), patch.dict(os.environ, {"OLLAMA_TIMEOUT_SECONDS": value}):
                with self.assertRaisesRegex(ValueError, "OLLAMA_TIMEOUT_SECONDS"):
                    OllamaProvider()

    def test_direct_and_url_wrapped_timeouts_name_the_model_and_limit(self):
        for error in (TimeoutError("timed out"), URLError(TimeoutError("timed out"))):
            with self.subTest(error=error), patch("summarizer.providers.ollama_provider.urllib.request.urlopen", side_effect=error):
                with self.assertRaises(TimeoutError) as caught:
                    OllamaProvider(model="gemma3:4b").summarize("Notícia original")
                self.assertIn("gemma3:4b", str(caught.exception))
                self.assertIn("900 segundos", str(caught.exception))
                self.assertIn("OLLAMA_TIMEOUT_SECONDS", str(caught.exception))

    def test_timeout_reading_the_response_body_is_also_descriptive(self):
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.side_effect = TimeoutError("timed out")
            with self.assertRaisesRegex(TimeoutError, "1200 segundos"):
                OllamaProvider(model="gemma3:4b", timeout=1200).summarize("Notícia original")

    def test_connection_and_http_errors_are_distinct_from_generation_timeout(self):
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen", side_effect=URLError(ConnectionRefusedError())):
            with self.assertRaisesRegex(ConnectionError, "Não foi possível conectar"):
                OllamaProvider().summarize("Notícia original")
        error = HTTPError("http://127.0.0.1:11434/api/chat", 500, "Failure", {}, BytesIO(b"model load failed"))
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500.*model load failed"):
                OllamaProvider().summarize("Notícia original")

    def test_real_slow_http_response_respects_timeout_and_returns_useful_error(self):
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                threading.Event().wait(.15)
                self.send_response(200)
                self.end_headers()
                try:
                    self.wfile.write(b"{}")
                except BrokenPipeError:
                    pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        try:
            provider = OllamaProvider(model="gemma3:4b", url=f"http://127.0.0.1:{server.server_port}/api/chat", timeout=.03)
            with self.assertRaisesRegex(TimeoutError, "gemma3:4b.*limite de espera"):
                provider.summarize("Notícia original")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
