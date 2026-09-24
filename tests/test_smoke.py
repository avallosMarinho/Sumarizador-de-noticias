import os
import unittest

from summarizer.contract import SUMMARY_JSON_SCHEMA, validate_summary
from summarizer.providers import DEFAULT_GEMINI_MODEL, HeuristicProvider, OllamaProvider
from summarizer.service import build_provider, summarize_text


SAMPLE = """
Biblioteca inaugura laboratório digital em Fortaleza

A Prefeitura de Fortaleza inaugurou em 9 de setembro de 2026 um laboratório
Digital na Biblioteca Municipal. A secretária Ana Souza informou que o espaço
terá computadores e oficinas gratuitas para estudantes.

O projeto atenderá inicialmente 300 alunos e funcionará de segunda a sexta-feira.
"""


class SmokeTest(unittest.TestCase):
    def test_expected_fields_in_heuristic_result(self):
        result = summarize_text(SAMPLE, provider="heuristic")
        for field in (
            "titulo", "resumo", "pontos_principais", "pessoas", "locais", "datas"
        ):
            self.assertIn(field, result)
        self.assertEqual(result["_meta"]["provider"], "heuristic")

    def test_provider_factory(self):
        self.assertIsInstance(build_provider("heuristic"), HeuristicProvider)
        ollama = build_provider("ollama", model="llama3.2:3b")
        self.assertIsInstance(ollama, OllamaProvider)
        self.assertEqual(ollama.model, "llama3.2:3b")

    def test_contract_rejects_missing_fields(self):
        with self.assertRaises(ValueError):
            validate_summary({"titulo": "x"})

    def test_summary_schema_has_required_fields(self):
        self.assertEqual(SUMMARY_JSON_SCHEMA["type"], "object")
        self.assertIn("titulo", SUMMARY_JSON_SCHEMA["required"])
        self.assertIn("resumo", SUMMARY_JSON_SCHEMA["required"])
        self.assertIn("pontos_principais", SUMMARY_JSON_SCHEMA["required"])
        self.assertIn("pessoas", SUMMARY_JSON_SCHEMA["required"])
        self.assertIn("locais", SUMMARY_JSON_SCHEMA["required"])
        self.assertIn("datas", SUMMARY_JSON_SCHEMA["required"])

    def test_default_gemini_model(self):
        self.assertEqual(DEFAULT_GEMINI_MODEL, "gemini-3.8-flash")

    def test_gemini_requires_key(self):
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaises(ValueError):
                build_provider("gemini")
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
