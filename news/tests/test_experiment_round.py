from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from news.models import Article, SummaryVersion
from news.services import CRITERION_KEYS, create_article, decide_version, enqueue_generation


class ExperimentRoundTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = get_user_model().objects.create_superuser("revisor", password="teste")

    def setUp(self):
        self.client.force_login(self.reviewer)
        self.url = reverse("admin:news_experiment_round")
        self.model = "qwen3:4b-instruct"

    def register(self, number):
        article = create_article({
            "original_title": f"Notícia {number}",
            "original_text": f"Notícia {number}\nTexto integral de exemplo.",
            "provider": "ollama",
            "model": "llama3.2:3b",
        }, self.reviewer)
        version = article.versions.get()
        version.status = SummaryVersion.Status.PENDING
        version.title = "Título gerado"
        version.summary = "Resumo original."
        version.save(update_fields=["status", "title", "summary"])
        return article, version

    def post_round(self, *texts, model="qwen3:4b-instruct"):
        return self.client.post(self.url, {
            "model": model,
            "text_file": [
                SimpleUploadedFile(f"noticia-{index}.txt", text.encode("utf-8-sig"))
                for index, text in enumerate(texts, start=1)
            ],
        })

    def test_round_links_fifteen_generations_to_the_existing_articles(self):
        entries = [self.register(number) for number in range(15)]
        first_article, first_version = entries[0]
        decide_version(first_version, self.reviewer, "approve", criteria={key: True for key in CRITERION_KEYS})

        response = self.post_round(*(article.original_text for article, _ in entries))
        self.assertRedirects(response, reverse("admin:index"))
        self.assertContains(self.client.get(self.url), "Adicionar rodada à fila")
        self.assertEqual(Article.objects.count(), 15)
        self.assertEqual(SummaryVersion.objects.count(), 30)
        queued = SummaryVersion.objects.filter(status="queued").order_by("created_at", "pk").values_list(
            "article_id", "number", "requested_provider", "requested_model",
        )
        self.assertEqual(list(queued), [(article.pk, 2, "ollama", self.model) for article, _ in entries])
        first_article.refresh_from_db()
        self.assertEqual(first_article.public_version_id, first_version.pk)
        self.assertEqual(SummaryVersion.objects.get(pk=first_version.pk).summary, "Resumo original.")

    def test_unregistered_and_duplicate_files_do_not_partially_enqueue(self):
        article, _ = self.register(1)
        for text in ("Notícia ainda não cadastrada", article.original_text):
            with self.subTest(text=text):
                response = self.post_round(article.original_text, text)
                self.assertContains(response, "noticia-2.txt")
                self.assertEqual(SummaryVersion.objects.count(), 1)

    def test_busy_article_rolls_back_the_round(self):
        first, _ = self.register(1)
        busy, _ = self.register(2)
        enqueue_generation(busy, self.reviewer, provider="ollama", model="gemma3:4b")
        response = self.post_round(first.original_text, busy.original_text)
        self.assertContains(response, "já tem uma geração na fila ou em andamento")
        self.assertFalse(SummaryVersion.objects.filter(requested_model=self.model).exists())
        first.refresh_from_db()
        self.assertEqual(first.version_counter, 1)

    def test_round_requires_an_explicit_model(self):
        article, _ = self.register(1)
        response = self.post_round(article.original_text, model="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("model", response.context["form"].errors)
        self.assertEqual(SummaryVersion.objects.count(), 1)
