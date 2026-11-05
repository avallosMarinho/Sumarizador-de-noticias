import json
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from news.forms import ArticleForm
from news.models import Article, SummaryVersion
from news.processing import process_next
from news.services import CRITERION_KEYS, create_article, decide_version, edit_version

TEXT = "Título da notícia\nTexto da notícia com informações para sumarização."
SUMMARY = {"titulo": "Título gerado", "resumo": "Resumo de teste.", "pontos_principais": [], "pessoas": [], "locais": [], "datas": []}


class ExperimentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("pesquisador", password="teste")

    def setUp(self):
        self.client.force_login(self.user)

    def create(self, data):
        response = self.client.post(reverse("admin:news_create"), data)
        self.assertEqual(response.status_code, 302)
        return Article.objects.get()

    def test_text_only_defaults_to_local_and_does_not_publish(self):
        article = self.create({"original_text": TEXT})
        self.assertEqual(article.original_title, "Título da notícia")
        self.assertEqual(article.source_name, "")
        self.assertEqual(article.versions.get().requested_provider, "ollama")
        self.assertIsNone(article.public_version_id)

    def test_txt_only_creates_version_and_keeps_full_text(self):
        article = self.create({"text_file": SimpleUploadedFile("noticia.txt", TEXT.encode("utf-8-sig"))})
        self.assertEqual(article.original_text, TEXT)
        self.assertEqual(article.original_title, "Título da notícia")
        self.assertEqual(article.versions.get().status, "queued")

    def test_input_validation_still_blocks_invalid_uploads_and_duplicates(self):
        self.assertFalse(ArticleForm({}).is_valid())
        self.assertFalse(ArticleForm({"original_text": TEXT}, {"text_file": SimpleUploadedFile("a.txt", b"abc")}).is_valid())
        for name, content in [("a.pdf", b"abc"), ("a.txt", b""), ("a.txt", b"abc\x00"), ("a.txt", b"x" * (1024*1024+1))]:
            with self.subTest(name=name, size=len(content)):
                self.assertFalse(ArticleForm({}, {"text_file": SimpleUploadedFile(name, content)}).is_valid())
        self.create({"original_text": TEXT})
        self.assertFalse(ArticleForm({"original_text": TEXT}).is_valid())

    def test_explicit_choices_preserved_and_long_derived_title_bounded(self):
        form = ArticleForm({"original_text": "x" * 301, "provider": "heuristic", "model": "", "original_title": "Meu título"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["original_title"], "Meu título")
        self.assertEqual(form.cleaned_data["provider"], "heuristic")
        form = ArticleForm({"original_text": "x" * 301})
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data["original_title"]), 300)

    def test_ollama_metrics_saved_rendered_and_preserved_after_edit(self):
        article = self.create({"original_text": TEXT, "model": "llama3.2:3b"})
        body = {"message": {"content": json.dumps(SUMMARY)}, "model": "llama3.2:3b",
                "prompt_eval_count": 200, "eval_count": 50, "eval_duration": 2_000_000_000,
                "load_duration": 500_000_000, "total_duration": 3_000_000_000}
        output = StringIO()
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen", return_value=BytesIO(json.dumps(body).encode())):
            call_command("process_summaries", once=True, stdout=output)
        self.assertIn("iniciando geração", output.getvalue())
        self.assertIn("concluída; pendente de revisão", output.getvalue())
        version = article.versions.get()
        self.assertEqual(version.generated_output["_meta"]["ollama"]["tokens_por_segundo"], 25)
        self.assertIsNotNone(version.duration_seconds)
        response = self.client.get(reverse("admin:news_review", args=[article.pk]))
        self.assertContains(response, "Tokens de entrada (prompt completo)")
        self.assertContains(response, "200")
        self.assertContains(response, "Carregamento do modelo (s)")
        self.assertIn(("Carregamento do modelo (s)", .5), version.generation_metrics)
        edited = edit_version(version, {"title": "Editado", "summary": "Resumo editado", "points": [], "people": [], "places": [], "dates": []}, self.user)
        self.assertEqual(edited.generated_output, version.generated_output)
        self.assertContains(self.client.get(reverse("admin:news_review", args=[article.pk])), "Tempo da geração de origem")
        decide_version(version, self.user, "approve", criteria={key: True for key in CRITERION_KEYS})
        self.assertContains(self.client.get(article.get_absolute_url()), "Resumo de teste.")

    def test_failure_logs_and_duration_are_saved(self):
        article = self.create({"original_text": TEXT})
        messages = []
        with patch("news.processing.summarize_text", side_effect=RuntimeError("Modelo indisponível")):
            process_next(report=messages.append)
        version = article.versions.get()
        self.assertEqual(version.status, "failed")
        self.assertIsNotNone(version.duration_seconds)
        self.assertIn("falha após", messages[-1])
        self.assertContains(self.client.get(reverse("admin:news_review", args=[article.pk])), "Dados da geração")
        self.assertIsNone(article.public_version_id)

    def test_invalid_model_json_preserves_tokens_without_entering_review(self):
        article = self.create({"original_text": TEXT})
        body = {"message": {"content": "não é json"}, "eval_count": 17, "eval_duration": 1000000000}
        with patch("summarizer.providers.ollama_provider.urllib.request.urlopen", return_value=BytesIO(json.dumps(body).encode())):
            process_next()
        version = article.versions.get()
        self.assertEqual(version.status, "failed")
        self.assertEqual(version.generated_output["_meta"]["ollama"]["eval_count"], 17)
        self.assertEqual(version.generated_output["_resposta_ollama"], "não é json")
        self.assertIsNone(article.public_version_id)

    def test_new_article_remembers_latest_local_model_for_the_current_reviewer(self):
        endpoint = reverse("admin:news_create")
        self.assertEqual(self.client.get(endpoint).context["form"]["model"].value(), "")
        self.create({"original_text": TEXT, "model": "llama3.2:3b"})
        self.client.post(endpoint, {"original_text": TEXT + " Outra notícia.", "provider": "auto", "model": "gemma3:4b"})
        self.client.post(endpoint, {"original_text": TEXT + " Terceira notícia.", "provider": "gemini", "model": "gemini-flash"})
        other = get_user_model().objects.create_superuser("outro")
        self.client.force_login(other)
        self.assertEqual(self.client.get(endpoint).context["form"]["model"].value(), "")
        self.client.post(endpoint, {"original_text": TEXT + " Outra conta.", "model": "qwen3:4b"})
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(endpoint).context["form"]["model"].value(), "gemma3:4b")

    def test_upload_batch_queues_each_file_with_the_selected_model(self):
        endpoint = reverse("admin:news_create")
        self.assertContains(self.client.get(endpoint), 'name="text_file" accept=".txt" multiple')
        titles = [f"Notícia {number}" for number in range(15)]
        response = self.client.post(endpoint, {
            "text_file": [SimpleUploadedFile(f"{number}.txt", f"{title}\nTexto completo.".encode())
                          for number, title in enumerate(titles)],
            "model": "llama3.2:3b",
        }, follow=True)
        self.assertRedirects(response, reverse("admin:index"))
        self.assertContains(response, "15 notícias salvas e adicionadas à fila")
        versions = SummaryVersion.objects.order_by("created_at").values_list(
            "article__original_title", "requested_model", "status", "article__public_version_id",
        )
        self.assertEqual(list(versions), [(title, "llama3.2:3b", "queued", None) for title in titles])

    def test_invalid_or_duplicate_file_keeps_entire_batch_out_of_queue(self):
        endpoint = reverse("admin:news_create")
        self.create({"original_text": TEXT})
        for invalid, content in [("repetido.txt", TEXT.encode()), ("invalido.pdf", b"nao e txt"),
                                 ("vazio.txt", b"   "), ("igual.txt", b"Noticia nova")]:
            with self.subTest(file=invalid):
                response = self.client.post(endpoint, {
                    "text_file": [SimpleUploadedFile("novo.txt", b"Noticia nova"), SimpleUploadedFile(invalid, content)],
                    "model": "gemma3:4b",
                })
                self.assertContains(response, invalid)
                self.assertEqual(response.context["form"]["model"].value(), "gemma3:4b")
                self.assertEqual(Article.objects.count(), 1)
                self.assertEqual(SummaryVersion.objects.count(), 1)

    def test_database_error_rolls_back_articles_already_added_in_the_batch(self):
        def fail_second(data, user):
            if data["original_title"] == "Segunda":
                raise ValidationError("A segunda notícia já está cadastrada.")
            return create_article(data, user)

        with patch("news.admin.create_article", side_effect=fail_second):
            response = self.client.post(reverse("admin:news_create"), {
                "text_file": [SimpleUploadedFile("1.txt", b"Primeira"), SimpleUploadedFile("2.txt", b"Segunda")],
            })
        self.assertContains(response, "A segunda notícia já está cadastrada.")
        self.assertFalse(Article.objects.exists())
        self.assertFalse(SummaryVersion.objects.exists())
