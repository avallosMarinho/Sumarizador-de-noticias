"""Um processador local por banco; a fila sobrevive à reinicialização."""
import fcntl
from pathlib import Path
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from news.models import SummaryVersion
from news.processing import process_next


class Command(BaseCommand):
    help = "Processa os resumos em segundo plano (Linux/macOS)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Processa uma notícia e encerra.")
        parser.add_argument("--interval", type=float, default=2, help="Segundos entre verificações da fila.")

    def handle(self, *args, **options):
        if options["interval"] <= 0:
            raise CommandError("O intervalo deve ser maior que zero.")
        lock_path = Path(settings.DATABASES["default"]["NAME"]).with_suffix(".worker.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CommandError("Já existe um processador usando este banco.") from exc
            # O lock garante que não há outro processador local em execução.
            recovered = SummaryVersion.objects.filter(status="processing").update(
                status="failed", finished_at=timezone.now(),
                error_message="A geração foi interrompida antes da conclusão. Solicite uma nova geração.",
            )
            if recovered:
                self.stdout.write(f"{recovered} geração(ões) interrompida(s) marcada(s) para nova tentativa.")
            self.stdout.write("Processador ativo. Aguardando notícias; Ctrl+C encerra.")
            try:
                while True:
                    close_old_connections()
                    processed = process_next()
                    if options["once"]:
                        break
                    if not processed:
                        time.sleep(options["interval"])
            except KeyboardInterrupt:
                self.stdout.write("Processador encerrado.")
