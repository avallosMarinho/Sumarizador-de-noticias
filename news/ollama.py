"""Consulta leve dos modelos disponíveis no mesmo Ollama usado pelo sumarizador."""
import json
from http.client import HTTPException
from urllib.parse import urljoin
from urllib.request import urlopen

from summarizer.providers.ollama_provider import OLLAMA_URL


class ModelListUnavailable(Exception):
    pass


def list_installed_models():
    try:
        with urlopen(urljoin(OLLAMA_URL, "/api/tags"), timeout=2) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ValueError("Lista de modelos inválida.")
    except (OSError, ValueError, HTTPException) as exc:
        raise ModelListUnavailable(
            "Não foi possível consultar os modelos instalados. "
            "Confirme se o Ollama está em execução e atualize a lista. "
            "Você também pode informar manualmente o nome de um modelo instalado."
        ) from exc

    names = set()
    for item in data["models"]:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and name and len(name) <= 200 and not any(char.isspace() for char in name):
            names.add(name)
    return sorted(names)
