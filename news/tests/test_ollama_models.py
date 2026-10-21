import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from news.processing import process_next
from news.services import create_article
from summarizer.providers import DEFAULT_OLLAMA_MODEL


class InstalledModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = get_user_model().objects.create_user("model-reviewer", is_staff=True)
        cls.reviewer.user_permissions.add(Permission.objects.get(codename="review_summary"))
        cls.staff = get_user_model().objects.create_user("model-no-permission", is_staff=True)

    def setUp(self):
        self.client.force_login(self.reviewer)
        self.endpoint = reverse("admin:news_ollama_models")

    def get_models(self, data):
        with patch("news.ollama.urlopen", return_value=BytesIO(json.dumps(data).encode())) as request:
            response = self.client.get(self.endpoint)
        return response, request

    def test_lists_installed_tags_preserving_aliases_but_not_duplicate_names(self):
        response, request = self.get_models({"models": [
            {"name": "llama3.2:latest", "digest": "same-content"},
            {"name": "llama3.2:3b", "digest": "same-content"},
            {"name": "llama3.2:3b"},
        ]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "models": ["llama3.2:3b", "llama3.2:latest"], "default_model": "llama3.2:3b",
        })
        request.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=2)
        self.assertIn("no-store", response["Cache-Control"])

    def test_default_model_is_preferred_only_if_installed(self):
        response, _ = self.get_models({"models": [{"name": "gemma3:4b"}, {"name": DEFAULT_OLLAMA_MODEL}]})
        self.assertEqual(response.json()["default_model"], DEFAULT_OLLAMA_MODEL)
        response, _ = self.get_models({"models": []})
        self.assertEqual(response.json(), {"models": [], "default_model": ""})

    def test_refresh_reads_current_installations_instead_of_a_cached_list(self):
        first, _ = self.get_models({"models": [{"name": "llama3.2:3b"}]})
        second, _ = self.get_models({"models": [{"name": "gemma3:4b"}]})
        self.assertEqual(first.json()["models"], ["llama3.2:3b"])
        self.assertEqual(second.json()["models"], ["gemma3:4b"])

    def test_unavailable_service_returns_a_clear_error_without_model_suggestions(self):
        for error in (URLError("connection refused"), TimeoutError("timeout")):
            with self.subTest(error=error), patch("news.ollama.urlopen", side_effect=error):
                response = self.client.get(self.endpoint)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["models"], [])
                self.assertIn("Confirme se o Ollama está em execução", response.json()["error"])

    def test_invalid_service_response_is_handled_as_unavailable(self):
        for body in (b"invalid-json", b"[]", b"{}", b'{"models": {}}'):
            with self.subTest(body=body), patch("news.ollama.urlopen", return_value=BytesIO(body)):
                response = self.client.get(self.endpoint)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["models"], [])

    def test_invalid_model_entries_do_not_become_suggestions(self):
        response, _ = self.get_models({"models": [None, "invalid", {}, {"name": None},
                                               {"name": ""}, {"name": "name with spaces"},
                                               {"name": "a" * 201}, {"name": "llama3.2:3b"}]})
        self.assertEqual(response.json()["models"], ["llama3.2:3b"])

    def test_listing_requires_reviewer_permission_and_get(self):
        with patch("news.ollama.urlopen") as request:
            self.assertEqual(Client().get(self.endpoint).status_code, 302)
            denied = Client()
            denied.force_login(self.staff)
            self.assertEqual(denied.get(self.endpoint).status_code, 403)
            self.assertEqual(self.client.post(self.endpoint).status_code, 405)
            request.assert_not_called()

    def test_creation_and_regeneration_share_the_dynamic_picker(self):
        article = create_article({
            "original_title": "Teste de modelos", "original_text": "A biblioteca abriu inscrições para oficinas gratuitas.",
            "provider": "heuristic", "model": "",
        }, self.reviewer)
        process_next()
        with patch("news.ollama.urlopen") as request:
            for endpoint in (reverse("admin:news_create"), reverse("admin:news_review", args=[article.pk])):
                with self.subTest(endpoint=endpoint):
                    response = self.client.get(endpoint)
                    self.assertContains(response, "data-model-picker")
                    self.assertContains(response, self.endpoint)
                    self.assertContains(response, "Atualizar modelos instalados")
                    self.assertContains(response, 'name="provider"')
                    self.assertContains(response, 'name="model"')
                    self.assertContains(response, "news/models.js")
                    self.assertNotContains(response, '<option value="qwen3.5:4b">')
                    self.assertNotContains(response, '<option value="gemma3:4b">')
            request.assert_not_called()  # A página abre sem esperar a consulta ao serviço.
