# News Summarizer v0.1.1

A v0.1.1 prepara o projeto para comparar diferentes modelos locais do **Ollama**
e um modelo em nuvem pela **Gemini API**, sem mudar o restante da aplicação.

## O que mudou em relação à v0.1

- Foi criado um contrato comum `SummarizerProvider`.
- Ollama, Gemini e modo heurístico implementam a mesma interface.
- Foi criado um esquema único de saída para todos os modelos.
- Foi criado um prompt-base único para tornar a comparação mais justa.
- O programa registra `provider`, `modelo`, tempo de execução e tamanho da entrada.
- Gemini só é utilizado quando escolhido explicitamente; o modo `auto` não envia
  a notícia para serviços externos.

## Estrutura

```text
news_summarizer_v0_1_1/
├── app.py
├── exemplo_noticia.txt
├── README.md
├── summarizer/
│   ├── __init__.py
│   ├── contract.py
│   ├── heuristic.py
│   ├── reader.py
│   ├── service.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       ├── heuristic_provider.py
│       ├── ollama_provider.py
│       └── gemini_provider.py
└── tests/
    └── test_smoke.py
```

## Fluxo arquitetural

```text
noticia.txt
    ↓
reader.py
    ↓
service.py
    ↓
SummarizerProvider
    ├── OllamaProvider ─→ Qwen / Llama / Gemma / outro modelo local
    ├── GeminiProvider ─→ Gemini API
    └── HeuristicProvider
    ↓
mesmo contrato de saída
    ↓
JSON / terminal
```

## Testar sem instalar IA

```bash
python3 app.py exemplo_noticia.txt --provider heuristic
```

## Testar modelos locais pelo Ollama

O programa aceita qualquer modelo que já esteja disponível no seu Ollama.
Exemplos planejados para o experimento:

```bash
python3 app.py exemplo_noticia.txt --provider ollama --model qwen3.5:4b
python3 app.py exemplo_noticia.txt --provider ollama --model qwen3:4b-instruct
python3 app.py exemplo_noticia.txt --provider ollama --model llama3.2:3b
python3 app.py exemplo_noticia.txt --provider ollama --model gemma3:4b
```

Eles são executados **um por vez**. O código, a notícia e o formato de saída
continuam iguais; somente o modelo muda.

Se `--model` for omitido no Ollama, o padrão da v0.1.1 é:

```text
qwen3.5:4b
```

## Testar a Gemini API

A aplicação não grava a chave da API em nenhum arquivo. Defina a chave como uma
variável de ambiente no terminal:

```bash
export GEMINI_API_KEY="SUA_CHAVE_AQUI"
```

Depois execute:

```bash
python3 app.py exemplo_noticia.txt --provider gemini
```

O modelo Gemini padrão desta versão é (estável/GA em setembro de 2026):

```text
gemini-3.8-flash
```

Também é possível escolher outro modelo explicitamente:

```bash
python3 app.py exemplo_noticia.txt --provider gemini --model gemini-3.8-flash
```

A variável definida com `export` dura somente naquela sessão do terminal. Não
publique a chave em GitHub, artigos, prints ou arquivos do projeto.

## Gerar saída JSON

Funciona da mesma forma para qualquer provider:

```bash
python3 app.py exemplo_noticia.txt --provider heuristic --json
python3 app.py exemplo_noticia.txt --provider ollama --model llama3.2:3b --json
python3 app.py exemplo_noticia.txt --provider gemini --json
```

Todos devolvem os mesmos campos:

```json
{
  "titulo": "...",
  "resumo": "...",
  "pontos_principais": ["..."],
  "pessoas": ["..."],
  "locais": ["..."],
  "datas": ["..."],
  "_meta": {
    "provider": "...",
    "model": "...",
    "duracao_segundos": 0.0,
    "caracteres_entrada": 0
  }
}
```

O bloco `_meta` é informação experimental; ele não faz parte do conteúdo do
resumo.

## Por que esta organização é útil para o experimento

O projeto aplica o princípio de **baixo acoplamento**: `app.py` não precisa saber
como cada IA funciona. Ele pede a um provider que resuma o texto. Cada provider
faz sua integração específica e devolve o mesmo contrato.

Isso permite comparar modelos mantendo constantes várias condições do teste:

- mesma notícia;
- mesmo prompt-base;
- mesmos campos de saída;
- mesma aplicação;
- execução individual de cada modelo.

A variável principal passa a ser o modelo/provedor utilizado.

## Testes automatizados

```bash
python3 -m unittest discover -s tests -v
```

Os testes locais não fazem chamadas reais ao Ollama ou à Gemini API.
