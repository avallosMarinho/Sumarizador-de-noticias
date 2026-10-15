from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from news.services import create_article


class Command(BaseCommand):
    help = "Cadastra uma notícia fictícia para testar o fluxo, sem publicar automaticamente."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Usuário revisor já cadastrado.")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if not user:
            raise CommandError("Usuário não encontrado. Execute createsuperuser primeiro.")
        data = {
            "original_title": "Campus Exemplo promove oficina gratuita de Python",
            "source_name": "Demonstração · notícia fictícia",
            "source_url": "", "source_date": None, "provider": "heuristic", "model": "",
            "original_text": (
                "Campus Exemplo promove oficina gratuita de Python\n\n"
                "O Campus Exemplo realizará uma oficina gratuita de Python em 22 de outubro, "
                "das 14h às 17h, no Laboratório 2. Serão ofertadas 20 vagas para estudantes de graduação. "
                "As inscrições encerram em 20 de outubro. A atividade inclui exercícios práticos "
                "sobre variáveis, condições e repetições."
            ),
        }
        try:
            article = create_article(data, user)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Notícia de demonstração cadastrada: {article.pk}. Aguarda geração e revisão."))
