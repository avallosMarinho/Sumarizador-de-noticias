from pathlib import Path


def read_txt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    if path.suffix.lower() != ".txt":
        raise ValueError("A versão 0.1 aceita apenas arquivos .txt.")

    data = path.read_bytes()
    if not data:
        raise ValueError("O arquivo está vazio.")

    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    for encoding in encodings:
        try:
            text = data.decode(encoding)
            text = text.strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue

    raise ValueError("Não foi possível decodificar o arquivo de texto.")
