from pathlib import Path
from urllib.parse import urlsplit

from django import forms

from .models import Article, Review
from .services import content_fingerprint, normalize_url

MAX_TEXT_LENGTH = 120_000
CRITERIA = {
    "fidelity": "Fidelidade: fatos, nomes, datas e números conferem com o original.",
    "coverage": "Cobertura: as informações essenciais foram preservadas.",
    "conciseness": "Concisão: o texto está breve e sem detalhes acessórios.",
    "coherence": "Coerência: a leitura é clara e as relações entre os fatos estão corretas.",
    "redundancy": "Ausência de redundância: o texto evita repetições.",
}


class GenerationForm(forms.Form):
    provider = forms.ChoiceField(label="Como gerar", initial="ollama", choices=[
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

    def clean_model(self):
        value = self.cleaned_data["model"].strip()
        if any(char.isspace() for char in value):
            raise forms.ValidationError("O nome do modelo não deve conter espaços.")
        return value


class ArticleForm(GenerationForm):
    original_title = forms.CharField(label="Título original", max_length=300)
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
    text_file = forms.FileField(label="Ou importe um arquivo TXT", required=False)

    def clean_source_url(self):
        url = self.cleaned_data.get("source_url", "")
        if url and urlsplit(url).scheme not in {"http", "https"}:
            raise forms.ValidationError("Use um link HTTP ou HTTPS para a notícia.")
        return normalize_url(url)

    def clean_text_file(self):
        file = self.cleaned_data.get("text_file")
        if file and (Path(file.name).suffix.lower() != ".txt" or file.size > 1024 * 1024):
            raise forms.ValidationError("Envie um arquivo .txt de até 1 MB.")
        return file

    def clean(self):
        data = super().clean()
        text = data.get("original_text", "").strip()
        file = data.get("text_file")
        if text and file:
            raise forms.ValidationError("Cole o texto ou importe o TXT; use apenas uma dessas opções.")
        if file:
            raw = file.read(1024 * 1024 + 1)
            for encoding in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = raw.decode(encoding).strip()
                    break
                except UnicodeDecodeError:
                    continue
        if not text:
            raise forms.ValidationError("Informe o texto da notícia ou importe um TXT preenchido.")
        if len(text) > MAX_TEXT_LENGTH:
            raise forms.ValidationError("A notícia deve ter no máximo 120 mil caracteres. O texto não foi cortado.")
        if "\x00" in text:
            raise forms.ValidationError("O arquivo contém caracteres inválidos para um texto de notícia.")
        data["original_text"] = text
        fingerprint = content_fingerprint(text)
        if Article.objects.filter(fingerprint=fingerprint).exists():
            raise forms.ValidationError("Este texto já está cadastrado. Localize a notícia no painel para gerar outra versão.")
        if data.get("source_url") and Article.objects.filter(source_url=data["source_url"]).exists():
            self.add_error("source_url", "Este link já está cadastrado. Use a notícia existente no painel.")
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
    notes = forms.CharField(label="Observação ou motivo da rejeição", required=False, max_length=4000,
                           widget=forms.Textarea(attrs={"rows": 3}))
    fidelity = forms.BooleanField(label=CRITERIA["fidelity"], required=False)
    coverage = forms.BooleanField(label=CRITERIA["coverage"], required=False)
    conciseness = forms.BooleanField(label=CRITERIA["conciseness"], required=False)
    coherence = forms.BooleanField(label=CRITERIA["coherence"], required=False)
    redundancy = forms.BooleanField(label=CRITERIA["redundancy"], required=False)

    def clean(self):
        data = super().clean()
        if data.get("action") == Review.Action.APPROVE and not all(data.get(key) for key in CRITERIA):
            raise forms.ValidationError("Confira e marque os cinco critérios antes de aprovar a publicação.")
        if data.get("action") == Review.Action.REJECT and not data.get("notes", "").strip():
            self.add_error("notes", "Informe o motivo da rejeição.")
        return data


class WithdrawalForm(forms.Form):
    public_version = forms.IntegerField(widget=forms.HiddenInput)
    notes = forms.CharField(label="Motivo da retirada", max_length=4000,
                           widget=forms.Textarea(attrs={"rows": 2}))
