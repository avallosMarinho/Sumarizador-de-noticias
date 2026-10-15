import subprocess
import sys
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Inicia a página e o processador juntos no notebook; Ctrl+C encerra ambos."

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=8000)

    def handle(self, *args, **options):
        port = options["port"]
        if not 1024 <= port <= 65535:
            raise CommandError("Use uma porta entre 1024 e 65535.")
        call_command("migrate", check_unapplied=True, verbosity=0)
        manage = str(settings.BASE_DIR / "manage.py")
        children = []
        self.stdout.write(f"Página: http://127.0.0.1:{port}/\nRevisão: http://127.0.0.1:{port}/admin/")
        try:
            children.append(subprocess.Popen([sys.executable, manage, "process_summaries"]))
            children.append(subprocess.Popen([sys.executable, manage, "runserver", f"127.0.0.1:{port}", "--noreload"]))
            while all(child.poll() is None for child in children):
                time.sleep(0.5)
            raise CommandError("Um dos processos foi encerrado. Confira a mensagem acima e inicie novamente.")
        except KeyboardInterrupt:
            self.stdout.write("Encerrando a aplicação local…")
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
