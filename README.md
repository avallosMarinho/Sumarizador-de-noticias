# News Summarizer v0.1

Primeira versão funcional de um sumarizador de notícias.

## O que esta versão faz

Recebe um arquivo `.txt` contendo uma notícia e gera:

- `titulo`
- `resumo`
- `pontos_principais`
- `pessoas`
- `locais`
- `datas`

O programa possui dois motores:

1. **Ollama**: usa um modelo de linguagem executado localmente.
2. **Heurístico**: usa somente Python e funciona mesmo sem IA instalada.

O modo padrão é `auto`: primeiro tenta Ollama; se ele não estiver disponível,
cai automaticamente para o modo heurístico.

## Requisitos mínimos

- Python 3.10 ou superior.
- Nenhum pacote Python externo é obrigatório.

## Como executar imediatamente

Abra o terminal dentro da pasta do projeto e rode:

```bash
python3 app.py exemplo_noticia.txt
```

Como o padrão é `auto`, se você não tiver Ollama instalado o programa continuará
funcionando em modo heurístico.

Para forçar o modo sem IA:

```bash
python3 app.py exemplo_noticia.txt --provider heuristic
```

Para retornar apenas JSON:

```bash
python3 app.py exemplo_noticia.txt --provider heuristic --json
```

## Usando IA local com Ollama

O projeto já está preparado para conversar com um Ollama que esteja rodando em:

```text
http://127.0.0.1:11434
```

Depois de instalar o Ollama e baixar um modelo compatível, você pode executar:

```bash
python3 app.py exemplo_noticia.txt --provider ollama --model qwen3:4b
```

Você também pode informar outro modelo disponível no seu Ollama:

```bash
python3 app.py exemplo_noticia.txt --provider ollama --model SEU_MODELO
```

## Estrutura do projeto

```text
news_summarizer_v0_1/
├── app.py
├── exemplo_noticia.txt
├── README.md
├── summarizer/
│   ├── __init__.py
│   ├── heuristic.py
│   ├── ollama_provider.py
│   ├── reader.py
│   └── service.py
└── tests/
    └── test_smoke.py
```

## Rodando o teste

```bash
python3 -m unittest discover -s tests -v
```

## Arquitetura da v0.1

```text
arquivo .txt
    ↓
leitura e validação
    ↓
service.py
    ↓
Ollama local ───────────┐
    │                   │
    └─ se falhar ─→ modo heurístico
                        ↓
                 resultado estruturado
                        ↓
                  terminal / JSON
```

## Limitações conhecidas

O modo heurístico é propositalmente simples. Ele consegue gerar um resumo e
fazer extrações básicas, mas a identificação de nomes e locais pode conter
falsos positivos. O modo Ollama tende a produzir resultados bem melhores.

Esta v0.1 também aceita apenas `.txt`. HTML, URL, RSS, interface gráfica e banco
de dados ficam para versões futuras.

## Próxima evolução recomendada

A v0.2 pode acrescentar:

- entrada HTML;
- limpeza do conteúdo com Trafilatura;
- validação mais rígida da saída;
- interface simples;
- histórico local dos resumos.
