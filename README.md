# Notícias em resumo · versão web local

Aplicação Python para cadastrar notícias, gerar resumos, fazer revisão humana e
publicar os aprovados em uma página responsiva. O sumarizador original e seu CLI
continuam disponíveis.

## Começar no notebook (Linux)

Requer Python 3.10 ou superior. Dentro da pasta do repositório:

```bash
git fetch origin
git switch feature/interface-revisao-local
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runlocal
```

Se a criação do ambiente virtual falhar no Ubuntu por falta de `venv`, instale
o pacote `python3-venv` do sistema e repita esse passo.

- Página de leitura: http://127.0.0.1:8000/
- Painel da equipe: http://127.0.0.1:8000/admin/

Entre no painel com o usuário e a senha que você criou. `runlocal` inicia o servidor
e o processador de resumos juntos. Mantenha esse terminal aberto; `Ctrl+C` encerra
os dois. Para usar outra porta: `python manage.py runlocal --port 8001`.

Esta configuração foi preparada para uso local, com acesso pelo próprio notebook.
A hospedagem pública e o aplicativo mobile são evoluções posteriores.

## Experimentar o fluxo sem instalar um modelo

1. No painel, clique em **Nova notícia**.
2. Informe o título, a fonte e o link original, quando disponíveis.
3. Cole o texto completo **ou** importe um TXT. O link funciona como referência;
   o conteúdo do site não é extraído automaticamente.
4. Em **Como gerar**, escolha **Heurístico · experimentar sem IA** e salve.
5. Aguarde a geração. A tela atualiza automaticamente enquanto o resumo está na fila.
6. Compare original e resumo, confira também pontos principais, pessoas, locais e datas.
7. Marque os cinco critérios de qualidade e clique em **Aprovar e publicar**.
8. Abra a página de leitura para conferir o cartão publicado.

O modo heurístico serve para testar o funcionamento sem depender de uma IA; ele
não equivale à qualidade dos modelos que você está avaliando.

Também é possível criar uma notícia fictícia, sem publicar automaticamente:

```bash
python manage.py create_demo --username SEU_USUARIO
```

Execute em outro terminal com o ambiente virtual ativado, ou antes de `runlocal`.
Esse comando cadastra uma única notícia de demonstração; executar novamente avisa
que o texto já existe.

## Usar Ollama ou Gemini na interface

- **Ollama:** mantenha o serviço em execução no notebook. Escolha o provedor no
  formulário e informe o nome de um modelo já instalado, como `llama3.2:3b`.
  O padrão herdado do sumarizador é `qwen3.5:4b`.
- **Gemini:** configure `GEMINI_API_KEY` no ambiente do terminal **antes de iniciar
  `runlocal`**. Escolha Gemini no formulário. É possível informar o identificador
  do modelo disponível na sua conta; em branco, utiliza o padrão do código atual.
- **Automático local:** tenta Ollama e pode usar o modo heurístico se houver falha.
  O provedor efetivamente utilizado e a observação dessa alternativa ficam
  registrados nos dados de geração. Gemini só é chamado quando escolhido.

As chaves não são solicitadas pela interface nem armazenadas no banco. O resultado
da geração vai para revisão; nenhum provedor publica diretamente. A troca da
interface não altera o tempo de inferência do modelo.

## Revisão, versões e publicação

- **Editar como nova versão:** preserva o resultado original do modelo e cria uma
  versão pendente, mesmo quando o resumo anterior já está publicado.
- **Rejeitar com motivo:** registra a decisão e mantém essa versão fora da página pública.
- **Gerar outra versão:** usa novamente a notícia original, com o provedor escolhido.
- **Aprovar e publicar:** exige a confirmação dos cinco critérios e publica exatamente
  a versão visualizada. Registra responsável, data, observação e critérios confirmados.
- **Retirar publicação:** exige um motivo, remove a notícia da listagem e do endereço
  público e preserva todos os registros internos.

Uma versão aprovada permanece pública durante novas gerações, edições ou rejeições
de outras versões. Ela só é substituída por outra aprovação ou retirada explicitamente.
Falha técnica na geração é registrada separadamente de rejeição humana.

O painel tem histórico de versões, decisões, saída original, provedor solicitado,
provedor utilizado, modelo, duração e prompt. Os cadastros genéricos do Django Admin
são somente leitura para esses registros, preservando o fluxo de revisão.

O superusuário criado na instalação pode usar todas as funções. Para outra conta
de revisão, ative **Membro da equipe** e conceda a permissão
**Pode gerar, revisar e publicar resumos**, no cadastro de usuários do painel.
Não há autocadastro público.

## Dados locais e reinicialização

O SQLite fica em `data/db.sqlite3`. A pasta `data/` também guarda a chave local da
aplicação e o lock do processador e é ignorada pelo Git. Fechar a aplicação não
apaga notícias, versões nem decisões. Para backup, encerre `runlocal` e copie a
pasta `data/` para um local seguro. Para restaurar, recoloque a pasta com a aplicação
parada e use o mesmo projeto atualizado.

A fila também é persistente. Se o processador for interrompido durante uma geração,
ao reiniciar ele marca essa tentativa como falha e permite solicitar outra geração.
Um lock impede executar dois processadores simultâneos para o mesmo banco local.

Para desenvolvimento com terminais separados, use:

```bash
python manage.py runserver 127.0.0.1:8000
```

Em outro terminal ativado:

```bash
python manage.py process_summaries
```

O processador também aceita `--once` para processar uma notícia e encerrar. A
chamada ao modelo ocorre fora da requisição web e fora de transações longas do banco.

## Verificar a implementação

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test news.tests
python -m unittest discover -s tests -v
```

Os testes da versão web incluem geração heurística real, importação de TXT,
aprovação, rejeição, edições, preservação da publicação anterior, retirada,
duplicatas, falhas dos provedores, permissões, proteção CSRF e acesso público.
Não fazem chamadas reais aos serviços Ollama ou Gemini.

## Organização da versão web

| Pasta/arquivo | Responsabilidade |
|---|---|
| `summarizer/` e `app.py` | Motor e CLI já existentes |
| `newsroom/` e `manage.py` | Configuração e inicialização Django |
| `news/models.py` | Notícia original, versões e decisões humanas |
| `news/services.py` | Regras de geração, revisão e publicação |
| `news/processing.py` | Processamento da fila usando o motor atual |
| `news/admin.py` | Painel autenticado da equipe |
| `news/views.py` | Listagem e detalhe públicos, somente com versões aprovadas |
| `news/templates/` e `news/static/` | Telas e estilos responsivos |

---

# Motor e CLI · v0.1.1

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
