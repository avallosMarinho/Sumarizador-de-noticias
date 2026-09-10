import unittest
from summarizer.heuristic import summarize_heuristic


class SmokeTest(unittest.TestCase):
    def test_expected_fields(self):
        text = """
Biblioteca inaugura laboratório digital em Fortaleza

A Prefeitura de Fortaleza inaugurou em 9 de setembro de 2026 um laboratório
digital na Biblioteca Municipal. A secretária Ana Souza informou que o espaço
terá computadores e oficinas gratuitas para estudantes.

O projeto atenderá inicialmente 300 alunos e funcionará de segunda a sexta-feira.
"""
        result = summarize_heuristic(text)

        self.assertIn("titulo", result)
        self.assertIn("resumo", result)
        self.assertIn("pontos_principais", result)
        self.assertIn("pessoas", result)
        self.assertIn("locais", result)
        self.assertIn("datas", result)
        self.assertTrue(result["resumo"])


if __name__ == "__main__":
    unittest.main()
