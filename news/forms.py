from pathlib import Path
from urllib.parse import urlsplit

from django import forms

from .models import Article, Review
from .services import content_fingerprint, normalize_url

MAX_TEXT_LENGTH = 120_000
MAX_TXT_BYTES = 1024 * 1024
MAX_TXT_FILES = 20


class GenerationForm(forms.Form):
    provider = forms.ChoiceField(label="Como gerar", initial="ollama", required=False, choices=[
        ("ollama", "Ollama · modelo local"),
        ("gemini", "Gemini · API"),
        ("heuristic", "Heurístico · experimentar sem IA"),
        ("auto", "Automático local · Ollama com alternativa heurística"),
    ])
    model = forms.CharField(
        label="Modelo", required=False, max_length=200,
        help_text="Escolha um modelo instalado no Ollama. Para Gemini, informe o identificador do modelo ou deixe vazio para usar o padrão.",
        widget=forms.TextInput(attrs={
            "placeholder": "Escolha um modelo instalado", "list": "model-options",
            "aria-describedby": "model-help model-status",
        }),
    )

    def clean_provider(self):
        return self.cleaned_data.get("provider") or "ollama"

    def clean_model(self):
        value = self.cleaned_data["model"].strip()
        if any(char.isspace() for char in value):
            raise forms.ValidationError("O nome do modelo não deve conter espaços.")
        return value


class MultipleTxtInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class TxtFilesField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        if len(files) > MAX_TXT_FILES:
            raise forms.ValidationError(f"Envie até {MAX_TXT_FILES} arquivos por vez.")
        cleaned = []
        for upload in files:
            try:
                file = super().clean(upload, initial)
                if Path(file.name).suffix.lower() != ".txt" or file.size > MAX_TXT_BYTES:
                    raise forms.ValidationError("Envie um arquivo .txt de até 1 MB.")
            except forms.ValidationError as exc:
                raise forms.ValidationError(f"{upload.name}: {exc.messages[0]}") from exc
            cleaned.append(file)
        return cleaned


def read_uploaded_text(file):
    raw = file.read(MAX_TXT_BYTES + 1)
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue


class ArticleForm(GenerationForm):
    max_txt_files = MAX_TXT_FILES
    original_title = forms.CharField(label="Título original (opcional)", max_length=300, required=False,
        help_text="Se vazio, usamos a primeira linha do texto como identificação inicial.")
    source_name = forms.CharField(label="Fonte", max_length=200, required=False)
    source_url = forms.URLField(label="Link para a notícia completa", max_length=1000, required=False)
    source_date = forms.DateField(
        label="Data da notícia original", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    original_text = forms.CharField(
        label="Texto da notícia", required=False, max_length=MAX_TEXT_LENGTH,
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "Cole a notícia completa aqui…"}),
    )
    text_file = TxtFilesField(
        label="Ou envie um ou mais arquivos TXT", required=False,
        widget=MultipleTxtInput(attrs={"accept": ".txt"}),
    )

    def clean_source_url(self):
        url = self.cleaned_data.get("source_url", "")
        if url and urlsplit(url).scheme not in {"http", "https"}:
            raise forms.ValidationError("Use um link HTTP ou HTTPS para a notícia.")
        return normalize_url(url)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        text = data.get("original_text", "")
        files = data["text_file"]
        if text and files:
            raise forms.ValidationError("Cole o texto ou envie os arquivos TXT. Use apenas uma dessas opções.")
        if len(files) > 1 and any(data.get(key) for key in ("original_title", "source_name", "source_url", "source_date")):
            raise forms.ValidationError("Deixe a identificação em branco ao enviar vários arquivos. Cada notícia usará a primeira linha do seu TXT como título.")
        if data.get("source_url"):
            linked = Article.objects.filter(source_url=data["source_url"]).only("trashed_at").first()
            if linked and linked.trashed_at:
                self.add_error("source_url", "Este link pertence a uma notícia na lixeira. Restaure a notícia para usá-la.")
            elif linked:
                self.add_error("source_url", "Este link já está cadastrado. Use a notícia existente no painel.")

        inputs = [(file.name, read_uploaded_text(file)) for file in files] if files else [("", text)]
        articles = {}
        names = {}
        for name, text in inputs:
            label = f"{name}: " if name else ""
            if not text:
                raise forms.ValidationError(label + "Informe o texto da notícia ou importe um TXT preenchido.")
            if len(text) > MAX_TEXT_LENGTH:
                raise forms.ValidationError(label + "A notícia deve ter no máximo 120 mil caracteres. O texto não foi cortado.")
            if "\x00" in text:
                raise forms.ValidationError(label + "O arquivo contém caracteres inválidos para um texto de notícia.")
            fingerprint = content_fingerprint(text)
            if fingerprint in articles:
                raise forms.ValidationError(f"{name} tem o mesmo texto de {names[fingerprint]}.")
            names[fingerprint] = name
            articles[fingerprint] = {
                **data, "original_text": text,
                "original_title": data.get("original_title") or text.splitlines()[0].strip()[:300],
            }
        existing = Article.objects.filter(fingerprint__in=articles).values_list("fingerprint", "trashed_at")
        for fingerprint, trashed_at in existing:
            name = names[fingerprint]
            label = f"{name}: " if name else ""
            if trashed_at:
                raise forms.ValidationError(label + "Esta notícia está na lixeira. Restaure-a para gerar outra versão.")
            raise forms.ValidationError(label + "Este texto já está cadastrado. Localize a notícia no painel para gerar outra versão.")
        data["articles"] = list(articles.values())
        if len(articles) == 1:
            data.update(data["articles"][0])
        return data


class EditSummaryForm(forms.Form):
    title = forms.CharField(label="Título", max_length=500)
    summary = forms.CharField(label="Resumo", max_length=6000, widget=forms.Textarea(attrs={"rows": 8}))
    points = forms.CharField(label="Pontos principais", required=False, widget=forms.Textarea(attrs={"rows": 4}))
    people = forms.CharField(label="Pessoas", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    places = forms.CharField(label="Locais", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    dates = forms.CharField(label="Datas", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        data = super().clean()
        for key in ("points", "people", "places", "dates"):
            data[key] = [line.strip() for line in data.get(key, "").splitlines() if line.strip()]
        return data


class DecisionForm(forms.Form):
    action = forms.ChoiceField(choices=[(Review.Action.APPROVE, "Aprovar"), (Review.Action.REJECT, "Rejeitar")])
    notes = forms.CharField(
        label="Observação ou motivo da rejeição (opcional)", required=False, max_length=4000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class WithdrawalForm(forms.Form):
    public_version = forms.IntegerField(widget=forms.HiddenInput)
    notes = forms.CharField(label="Motivo da retirada", max_length=4000,
                           widget=forms.Textarea(attrs={"rows": 2}))
