import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from news.processing import process_next
from news.services import create_article


class GenerationTimeoutTests(TestCase):
    def test_timeout_is_saved_with_details_and_does_not_block_the_next_article(self):
        reviewer = get_user_model().objects.create_user("timeout-reviewer", is_staff=True)
        reviewer.user_permissions.add(Permission.objects.get(codename="review_summary"))
        original = "A biblioteca oferece oficinas gratuitas para estudantes em 22 de outubro."
        article = create_article({"original_title": "Oficinas", "original_text": original,
                                  "provider": "ollama", "model": "gemma3:4b"}, reviewer)
        next_article = create_article({"original_title": "Novo laboratório", "original_text": "O campus inaugurou um laboratório para estudantes.",
                                       "provider": "heuristic", "model": ""}, reviewer)
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT_SECONDS": "900"}), patch(
            "summarizer.providers.ollama_provider.urllib.request.urlopen", side_effect=TimeoutError("timed out")
        ):
            self.assertTrue(process_next())
        version = article.versions.get()
        self.assertEqual(version.status, "failed")
        self.assertIn("gemma3:4b", version.error_message)
        self.assertIn("900 segundos", version.error_message)
        article.refresh_from_db()
        self.assertEqual(article.original_text, original)
        self.assertIsNone(article.public_version_id)
        self.client.force_login(reviewer)
        response = self.client.get(reverse("admin:news_review", args=[article.pk]))
        self.assertContains(response, "A geração não foi concluída")
        self.assertContains(response, "900 segundos")
        self.assertTrue(process_next())
        self.assertEqual(next_article.versions.get().status, "pending")
