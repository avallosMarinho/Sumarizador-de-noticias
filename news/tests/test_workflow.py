from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from news.forms import ArticleForm
from news.models import Article, Review, SummaryVersion
from news.processing import process_next
from news.services import create_article, decide_version, edit_version, enqueue_generation, withdraw_article

TEXT = (
    "Biblioteca oferece oficinas de programação\n\n"
    "A biblioteca do Campus Exemplo realizará oficinas gratuitas de programação em 22 de outubro. "
    "Serão ofertadas 30 vagas para estudantes. As inscrições vão até 20 de outubro. "
    "As atividades ocorrerão no Laboratório 2, das 14h às 17h."
)


class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = get_user_model().objects.create_user("revisor", password="senha-de-teste-2026", is_staff=True)
        cls.reviewer.user_permissions.add(Permission.objects.get(codename="review_summary"))
        cls.staff = get_user_model().objects.create_user("sem-permissao", password="senha-de-teste-2026", is_staff=True)

    def setUp(self):
        self.client.force_login(self.reviewer)

    def create(self, suffix="", **kwargs):
        data = {
            "original_title": "Biblioteca oferece oficinas" + suffix,
            "source_name": "Campus Exemplo", "source_url": "", "source_date": None,
            "original_text": TEXT + suffix, "provider": "heuristic", "model": "", **kwargs,
        }
        return create_article(data, self.reviewer)

    def ready(self, suffix=""):
        article = self.create(suffix)
        self.assertTrue(process_next())
        version = article.versions.get()
        self.assertEqual(version.status, SummaryVersion.Status.PENDING)
        return article, version

    def approve(self, version):
        decide_version(version, self.reviewer, Review.Action.APPROVE)
        version.refresh_from_db()

    def test_creation_and_real_heuristic_processing_do_not_publish(self):
        article, version = self.ready()
        self.assertTrue(version.generated_output)
        self.assertEqual(version.provider, "heuristic")
        self.assertIsNone(article.public_version_id)
        public = Client()
        self.assertNotContains(public.get("/"), version.title)
        self.assertEqual(public.get(article.get_absolute_url()).status_code, 404)

    def test_exact_reviewed_version_is_published_and_audited(self):
        article, version = self.ready()
        review_page = self.client.get(reverse("admin:news_review", args=[article.pk]))
        self.assertContains(review_page, "Observação ou motivo da rejeição (opcional)")
        self.assertNotContains(review_page, 'type="checkbox"')
        response = self.client.post(reverse("admin:news_decide", args=[version.pk]), {"action": "approve"})
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.public_version_id, version.pk)
        review = Review.objects.get(version=version)
        self.assertEqual(review.reviewer, self.reviewer)
        self.assertEqual(review.notes, "")
        self.assertEqual(review.criteria, {})
        self.assertContains(Client().get(article.get_absolute_url()), version.summary)

    def test_approval_requires_a_complete_summary(self):
        article, version = self.ready()
        SummaryVersion.objects.filter(pk=version.pk).update(summary="")
        response = self.client.post(reverse("admin:news_decide", args=[version.pk]), {"action": "approve"})
        self.assertContains(response, "O título e o resumo precisam estar preenchidos.")
        article.refresh_from_db()
        self.assertIsNone(article.public_version_id)
        self.assertFalse(Review.objects.exists())

    def test_rejection_without_reason_stays_private(self):
        article, version = self.ready()
        endpoint = reverse("admin:news_decide", args=[version.pk])
        response = self.client.post(endpoint, {"action": "reject"})
        self.assertEqual(response.status_code, 302)
        version.refresh_from_db()
        self.assertEqual(version.status, SummaryVersion.Status.REJECTED)
        self.assertEqual(Review.objects.get(version=version).notes, "")
        self.assertEqual(Client().get(article.get_absolute_url()).status_code, 404)

    def test_note_is_saved_with_either_decision_when_provided(self):
        for action in (Review.Action.APPROVE, Review.Action.REJECT):
            with self.subTest(action=action):
                article, version = self.ready(f" {action}")
                note = "Observação da equipe editorial."
                response = self.client.post(reverse("admin:news_decide", args=[version.pk]), {
                    "action": action, "notes": note,
                })
                self.assertRedirects(response, reverse("admin:news_review", args=[article.pk]))
                self.assertEqual(Review.objects.get(version=version).notes, note)

    def test_regeneration_preserves_publication_and_original_text(self):
        article, version = self.ready()
        self.approve(version)
        pending = enqueue_generation(article, self.reviewer, "heuristic")
        self.assertEqual(pending.number, 2)
        with patch("news.processing.summarize_text", side_effect=ConnectionError("Serviço indisponível")) as provider:
            process_next()
            self.assertEqual(provider.call_args.args[0], TEXT)
        pending.refresh_from_db()
        article.refresh_from_db()
        self.assertEqual(pending.status, SummaryVersion.Status.FAILED)
        self.assertEqual(article.public_version_id, version.pk)
        self.assertContains(Client().get(article.get_absolute_url()), version.summary)
        self.assertEqual(enqueue_generation(article, self.reviewer, "heuristic").number, 3)

    def test_edit_creates_pending_version_and_preserves_raw_model_output(self):
        article, original = self.ready()
        self.approve(original)
        raw = deepcopy(original.generated_output)
        response = self.client.post(reverse("admin:news_edit", args=[original.pk]), {
            "title": "Título corrigido", "summary": "Resumo corrigido pelo revisor.",
            "points": "Fato um\nFato dois", "people": "", "places": "Campus Exemplo", "dates": "22 de outubro",
        })
        self.assertEqual(response.status_code, 302)
        edited = article.versions.get(number=2)
        self.assertEqual(edited.status, SummaryVersion.Status.PENDING)
        self.assertEqual(edited.origin, "human")
        self.assertEqual(edited.generated_output, raw)
        self.assertEqual(edited.points, ["Fato um", "Fato dois"])
        original.refresh_from_db()
        self.assertNotEqual(original.title, edited.title)
        public = Client()
        self.assertNotContains(public.get(article.get_absolute_url()), edited.summary)
        self.approve(edited)
        self.assertContains(public.get(article.get_absolute_url()), edited.summary)

    def test_double_decision_is_rejected_without_rewriting_history(self):
        _, version = self.ready()
        self.approve(version)
        with self.assertRaises(ValidationError):
            decide_version(version, self.reviewer, Review.Action.REJECT, notes="Outra decisão")
        self.assertEqual(Review.objects.count(), 1)

    def test_failed_generation_is_distinct_from_human_rejection(self):
        article = self.create()
        with patch("news.processing.summarize_text", side_effect=RuntimeError("Modelo não encontrado")):
            process_next()
        version = article.versions.get()
        self.assertEqual(version.status, "failed")
        self.assertIn("Modelo não encontrado", version.error_message)
        self.assertFalse(Review.objects.exists())
        self.assertIsNone(article.public_version_id)

    def test_empty_model_output_cannot_enter_review_or_publication(self):
        article = self.create()
        result = {"titulo": "", "resumo": "", "pontos_principais": [], "pessoas": [], "locais": [], "datas": []}
        with patch("news.processing.summarize_text", return_value=result):
            process_next()
        self.assertEqual(article.versions.get().status, "failed")

    def test_duplicate_active_job_is_prevented(self):
        article = self.create()
        with self.assertRaises(ValidationError):
            enqueue_generation(article, self.reviewer, "heuristic")
        article.refresh_from_db()
        self.assertEqual(article.version_counter, 1)
        self.assertEqual(article.versions.count(), 1)

    def test_database_also_enforces_single_active_generation(self):
        article = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SummaryVersion.objects.create(article=article, number=2, created_by=self.reviewer, requested_provider="heuristic")

    def test_duplicate_text_and_tracking_variants_of_url_are_blocked(self):
        self.create(source_url="https://example.org/noticia/?utm_source=email#top")
        with self.assertRaises(ValidationError):
            self.create(" outro texto", source_url="https://example.org/noticia")
        self.assertEqual(Article.objects.count(), 1)
        form = ArticleForm({"original_title": "Outro título", "provider": "heuristic", "original_text": TEXT.upper()})
        self.assertFalse(form.is_valid())
        self.assertIn("já está cadastrado", str(form.non_field_errors()))

    def test_pasted_text_and_uploaded_file_are_mutually_exclusive(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = {"original_title": "Título", "provider": "heuristic", "original_text": TEXT}
        form = ArticleForm(data, {"text_file": SimpleUploadedFile("noticia.txt", TEXT.encode())})
        self.assertFalse(form.is_valid())

    def test_txt_upload_creates_persistent_job(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post(reverse("admin:news_create"), {
            "original_title": "Oficinas de programação", "provider": "heuristic",
            "text_file": SimpleUploadedFile("noticia.txt", TEXT.encode("utf-8-sig")),
        })
        self.assertEqual(response.status_code, 302)
        article = Article.objects.get()
        self.assertEqual(article.original_text, TEXT)
        self.assertEqual(article.versions.get().status, "queued")

    def test_withdrawal_removes_list_detail_and_search_but_keeps_history(self):
        article, version = self.ready()
        self.approve(version)
        article.refresh_from_db()
        withdraw_article(article, self.reviewer, "Correção na fonte original.")
        public = Client()
        self.assertNotContains(public.get("/"), version.title)
        self.assertNotContains(public.get("/", {"q": "oficinas"}), version.title)
        self.assertEqual(public.get(article.get_absolute_url()).status_code, 404)
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(article.versions.count(), 1)

    def test_stale_withdrawal_does_not_remove_a_new_publication(self):
        article, first = self.ready()
        self.approve(first)
        edited = edit_version(first, {
            "title": "Novo título", "summary": "Novo resumo", "points": [], "people": [], "places": [], "dates": [],
        }, self.reviewer)
        self.approve(edited)
        response = self.client.post(reverse("admin:news_withdraw", args=[article.pk]), {
            "withdrawal-notes": "Retirar a versão anterior", "withdrawal-public_version": first.pk,
        })
        self.assertContains(response, "versão publicada mudou")
        article.refresh_from_db()
        self.assertEqual(article.public_version_id, edited.pk)

    def test_unpublished_title_never_leaks_into_public_search(self):
        article, version = self.ready()
        self.approve(version)
        edit_version(version, {"title": "RascunhoSECRETO", "summary": "ConteúdoSECRETO", "points": [], "people": [], "places": [], "dates": []}, self.reviewer)
        response = Client().get("/", {"q": "RascunhoSECRETO"})
        self.assertNotContains(response, version.title)
        self.assertNotContains(Client().get(article.get_absolute_url()), "ConteúdoSECRETO")

    def test_publication_does_not_accept_version_from_another_article(self):
        first, version = self.ready()
        other = self.create(" outra notícia")
        self.approve(version)
        Article.objects.filter(pk=other.pk).update(public_version=version, published_at=first.created_at)
        self.assertEqual(Client().get(other.get_absolute_url()).status_code, 404)

    def test_anonymous_and_unauthorized_staff_cannot_review(self):
        article, version = self.ready()
        endpoints = [reverse("admin:index"), reverse("admin:news_create"), reverse("admin:news_review", args=[article.pk]), reverse("admin:news_edit", args=[version.pk])]
        for endpoint in endpoints:
            self.assertEqual(Client().get(endpoint).status_code, 302)
        denied = Client()
        denied.force_login(self.staff)
        for endpoint in endpoints:
            self.assertEqual(denied.get(endpoint).status_code, 403)
        self.assertEqual(denied.post(reverse("admin:news_decide", args=[version.pk]), {"action": "approve"}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            enqueue_generation(article, self.staff, "heuristic")

    def test_review_mutations_require_post_and_csrf(self):
        article, version = self.ready()
        for endpoint in [reverse("admin:news_generate", args=[article.pk]), reverse("admin:news_decide", args=[version.pk]), reverse("admin:news_withdraw", args=[article.pk])]:
            self.assertEqual(self.client.get(endpoint).status_code, 405)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.reviewer)
        self.assertEqual(protected.post(reverse("admin:news_decide", args=[version.pk]), {"action": "approve"}).status_code, 403)

    def test_generic_admin_cannot_edit_or_delete_editorial_records(self):
        article, version = self.ready()
        self.approve(version)
        self.assertEqual(self.client.post(reverse("admin:news_summaryversion_change", args=[version.pk]), {"status": "approved"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:news_article_delete", args=[article.pk])).status_code, 403)

    def test_invalid_or_cross_article_version_is_not_exposed(self):
        first, _ = self.ready()
        _, second = self.ready(" diferente")
        endpoint = reverse("admin:news_review", args=[first.pk])
        self.assertEqual(self.client.get(endpoint, {"versao": "invalida"}).status_code, 404)
        self.assertEqual(self.client.get(endpoint, {"versao": second.pk}).status_code, 404)

    def test_public_text_is_escaped(self):
        article, version = self.ready()
        version.title = '<script>alert("x")</script>'
        version.summary = '<img src=x onerror="alert(1)">'
        version.save(update_fields=["title", "summary"])
        self.approve(version)
        response = Client().get(article.get_absolute_url())
        self.assertNotContains(response, '<img src=x onerror=')
        self.assertContains(response, '&lt;img')

    def test_editorial_templates_render_each_state(self):
        article, version = self.ready()
        for status in SummaryVersion.Status.values:
            SummaryVersion.objects.filter(pk=version.pk).update(status=status)
            self.assertEqual(self.client.get(reverse("admin:news_review", args=[article.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:news_create")).status_code, 200)

    def test_dashboard_combines_queue_and_processing_and_preserves_search(self):
        queued = self.create(" fila")
        running = self.create(" gerando")
        SummaryVersion.objects.filter(article=running).update(status="processing")
        response = self.client.get(reverse("admin:index"), {"state": "processing"})
        self.assertEqual({a.pk for a in response.context["page_obj"]}, {queued.pk, running.pk})
        self.assertEqual(response.context["counts"]["processing"], 2)
        response = self.client.get(reverse("admin:index"), {"state": "processing", "q": "gerando"})
        self.assertEqual([a.pk for a in response.context["page_obj"]], [running.pk])
        self.assertContains(response, 'state=pending&amp;q=gerando')

    def test_dashboard_keeps_publication_visible_with_pending_new_version(self):
        article, version = self.ready()
        self.approve(version)
        enqueue_generation(article, self.reviewer, "heuristic")
        process_next()
        response = self.client.get(reverse("admin:index"), {"state": "published"})
        self.assertEqual([a.pk for a in response.context["page_obj"]], [article.pk])
        self.assertContains(response, "Versão 1 no ar")
        self.assertContains(response, "Pronta para revisão")
        self.assertContains(response, "Revisar")
        self.assertNotContains(response, 'id="nav-sidebar"')
        self.assertContains(response, "Ver página de notícias")

    def test_administration_menu_and_pages_require_superuser(self):
        response = self.client.get(reverse("admin:index"))
        self.assertNotContains(response, "Gerenciar acesso da equipe")
        for section in ["equipe", "registros"]:
            url = reverse("admin:news_administration", args=[section])
            self.assertEqual(self.client.get(url).status_code, 403)
        admin_user = get_user_model().objects.create_superuser("admin-teste", password="teste")
        self.client.force_login(admin_user)
        self.assertContains(self.client.get(reverse("admin:index")), "Gerenciar acesso da equipe")
        for section in ["equipe", "registros"]:
            response = self.client.get(reverse("admin:news_administration", args=[section]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Voltar ao painel")
        self.assertContains(self.client.get(reverse("admin:news_administration", args=["equipe"])), reverse("admin:auth_user_changelist"))

    def test_trash_confirmation_moves_only_the_selected_news_and_can_restore_it(self):
        article, version = self.ready(" para descartar")
        other, _ = self.ready(" para manter")
        endpoint = reverse("admin:news_trash", args=[article.pk])
        dashboard_url = reverse("admin:index") + "?q=Biblioteca&state=pending&page=1"
        confirmation = self.client.get(endpoint, {"q": "Biblioteca", "state": "pending", "page": 1})
        self.assertContains(confirmation, "Mover esta notícia para a lixeira?")
        self.assertContains(confirmation, article.original_title)
        self.assertContains(confirmation, "Cancelar")
        self.assertEqual(confirmation.context["return_url"], dashboard_url)
        article.refresh_from_db()
        self.assertIsNone(article.trashed_at)

        response = self.client.post(endpoint + "?q=Biblioteca&state=pending&page=1")
        self.assertRedirects(response, dashboard_url)
        listing = self.client.get(reverse("admin:index"))
        self.assertEqual([item.pk for item in listing.context["page_obj"]], [other.pk])
        self.assertEqual(listing.context["counts"]["all"], 1)
        self.assertEqual(listing.context["counts"]["pending"], 1)
        self.assertEqual(listing.context["counts"]["trash"], 1)
        trash = self.client.get(reverse("admin:index"), {"state": "trash"})
        self.assertEqual([item.pk for item in trash.context["page_obj"]], [article.pk])
        self.assertContains(trash, "Restaurar")
        self.assertEqual(article.versions.get().generated_output, version.generated_output)

        restore = reverse("admin:news_restore", args=[article.pk])
        self.assertEqual(self.client.get(restore).status_code, 405)
        self.assertRedirects(self.client.post(restore), reverse("admin:index") + "?state=trash")
        article.refresh_from_db()
        self.assertIsNone(article.trashed_at)
        self.assertEqual(article.versions.get().pk, version.pk)
        self.assertEqual(enqueue_generation(article, self.reviewer, "heuristic").number, 2)

    def test_trash_hides_a_publication_until_explicitly_restored(self):
        article, version = self.ready()
        self.approve(version)
        public = Client()
        self.assertContains(public.get(article.get_absolute_url()), version.summary)
        self.client.post(reverse("admin:news_trash", args=[article.pk]))
        self.assertNotContains(public.get("/"), version.title)
        self.assertEqual(public.get(article.get_absolute_url()).status_code, 404)
        trash = self.client.get(reverse("admin:index"), {"state": "trash"})
        self.assertContains(trash, "Restaurar e republicar")
        self.assertEqual(Review.objects.filter(version=version).count(), 1)

        self.client.post(reverse("admin:news_restore", args=[article.pk]))
        self.assertContains(public.get(article.get_absolute_url()), version.summary)
        article.refresh_from_db()
        self.assertEqual(article.public_version_id, version.pk)

    def test_trash_and_restore_require_editorial_permission_and_csrf(self):
        article, _ = self.ready()
        endpoint = reverse("admin:news_trash", args=[article.pk])
        restore = reverse("admin:news_restore", args=[article.pk])
        denied = Client()
        denied.force_login(self.staff)
        self.assertEqual(denied.get(endpoint).status_code, 403)
        self.assertEqual(denied.post(endpoint).status_code, 403)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.reviewer)
        self.assertEqual(protected.post(endpoint).status_code, 403)

        self.client.post(endpoint)
        self.assertEqual(denied.post(restore).status_code, 403)
        self.assertEqual(protected.post(restore).status_code, 403)
        article.refresh_from_db()
        self.assertIsNotNone(article.trashed_at)

    def test_trash_preserves_queued_and_processing_versions(self):
        article = self.create()
        endpoint = reverse("admin:news_trash", args=[article.pk])
        for status in (SummaryVersion.Status.QUEUED, SummaryVersion.Status.PROCESSING):
            with self.subTest(status=status):
                article.versions.update(status=status)
                self.assertContains(self.client.post(endpoint), "Aguarde a geração na fila ou em andamento")
                article.refresh_from_db()
                self.assertIsNone(article.trashed_at)
                self.assertEqual(article.versions.get().status, status)

    def test_trashed_news_rejects_new_versions_and_points_to_restore(self):
        article, version = self.ready()
        self.client.post(reverse("admin:news_trash", args=[article.pk]))
        self.assertEqual(self.client.get(reverse("admin:news_review", args=[article.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("admin:news_generate", args=[article.pk]), {
            "provider": "heuristic",
        }).status_code, 404)
        with self.assertRaises(ValidationError):
            enqueue_generation(article, self.reviewer, "heuristic")
        with self.assertRaises(ValidationError):
            decide_version(version, self.reviewer, Review.Action.APPROVE)
        form = ArticleForm({"original_text": article.original_text})
        self.assertFalse(form.is_valid())
        self.assertIn("Esta notícia está na lixeira", str(form.non_field_errors()))
        self.assertEqual(article.versions.count(), 1)
