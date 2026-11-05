import json
import unittest
from io import BytesIO
from unittest.mock import patch

from summarizer.providers.ollama_provider import OllamaProvider
from summarizer.service import summarize_text

SUMMARY = {"titulo": "Título", "resumo": "Resumo", "pontos_principais": [], "pessoas": [], "locais": [], "datas": []}


class MetricsTests(unittest.TestCase):
    def generate(self, **metrics):
        body = {"message": {"content": json.dumps(SUMMARY)}, **metrics}
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen", return_value=BytesIO(json.dumps(body).encode())):
            return summarize_text("Notícia", provider="ollama", model="teste:3b")

    def test_metrics_survive_service_with_ns_and_effective_model(self):
        result = self.generate(prompt_eval_count=20, eval_count=10, eval_duration=2_000_000_000,
                               load_duration=100_000_000, total_duration=3_000_000_000, model="teste:3b-q4")
        meta = result["_meta"]
        self.assertEqual(meta["model"], "teste:3b-q4")
        self.assertEqual(meta["caracteres_entrada"], 7)
        self.assertEqual(meta["ollama"]["tokens_por_segundo"], 5)
        self.assertEqual(meta["ollama"]["load_duration"], 100_000_000)
        self.assertEqual(meta["parametros_enviados"], {"temperature": 0})
        self.assertEqual(result["resumo"], "Resumo")

    def test_missing_zero_and_invalid_values_are_not_invented(self):
        meta = self.generate(eval_count=0, eval_duration=0, prompt_eval_count=-2, load_duration=True)["_meta"]["ollama"]
        self.assertEqual(meta, {"eval_count": 0, "eval_duration": 0})
        self.assertEqual(self.generate()["_meta"]["ollama"], {})

    def test_auto_total_includes_failed_attempt(self):
        with patch("summarizer.service.OllamaProvider", side_effect=ConnectionError("offline")), \
             patch("summarizer.service.perf_counter", side_effect=[0, 10, 12, 13]):
            result = summarize_text("Uma notícia para resumir.")
        self.assertEqual(result["_meta"]["duracao_segundos"], 13)
        self.assertTrue(result["_meta"]["fallback"])
        self.assertEqual(result["_meta"]["provider"], "heuristic")
