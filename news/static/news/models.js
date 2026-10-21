// Sugestões locais são consultadas no servidor, que acessa o Ollama do notebook.
document.querySelectorAll('[data-model-picker]').forEach((picker) => {
  const provider = picker.querySelector('[name="provider"]');
  const model = picker.querySelector('[name="model"]');
  const options = picker.querySelector('datalist');
  const help = picker.querySelector('[data-model-help]');
  const status = picker.querySelector('[data-model-status]');
  const refresh = picker.querySelector('[data-model-refresh]');
  const group = () => ['ollama', 'auto'].includes(provider.value) ? 'local' : provider.value;
  let activeGroup = group();
  let requestNumber = 0;
  const remembered = new Map([[activeGroup, model.value]]);

  async function loadModels() {
    const currentRequest = ++requestNumber;
    refresh.disabled = true;
    options.replaceChildren();
    status.textContent = 'Consultando modelos instalados…';
    try {
      const response = await fetch(picker.dataset.modelsUrl, {credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json();
      if (currentRequest !== requestNumber || group() !== 'local') return;
      if (!response.ok) throw new Error(data.error || 'Não foi possível consultar os modelos. Atualize a lista para tentar novamente.');
      for (const name of data.models) {
        const option = document.createElement('option');
        option.value = name;
        options.append(option);
      }
      // Usa somente um padrão que esteja instalado, sem trocar uma escolha já preenchida.
      if (!model.value && data.default_model) model.value = data.default_model;
      status.textContent = data.models.length
        ? `${data.models.length} modelo(s) instalado(s). Atualize a lista após baixar ou remover um modelo.`
        : 'Nenhum modelo instalado no Ollama. Baixe um modelo e atualize a lista.';
    } catch (error) {
      if (currentRequest === requestNumber && group() === 'local') {
        status.textContent = error.message.startsWith('Não foi possível')
          ? error.message
          : 'Não foi possível consultar os modelos. Confirme se o Ollama está em execução e atualize a lista. Você pode informar o nome manualmente.';
      }
    } finally {
      if (currentRequest === requestNumber) refresh.disabled = false;
    }
  }

  function updateProvider() {
    const nextGroup = group();
    if (nextGroup !== activeGroup) {
      remembered.set(activeGroup, model.value);
      model.value = remembered.get(nextGroup) || '';
      activeGroup = nextGroup;
    }
    ++requestNumber; // Respostas de uma seleção anterior não alteram o campo atual.
    options.replaceChildren();
    const local = activeGroup === 'local';
    refresh.hidden = !local;
    refresh.disabled = false;
    status.hidden = !local;
    status.textContent = '';
    model.disabled = activeGroup === 'heuristic';
    model.placeholder = local ? 'Escolha um modelo instalado' : 'Modelo Gemini (opcional)';
    help.textContent = local
      ? 'Escolha um dos modelos instalados no Ollama deste computador.'
      : activeGroup === 'gemini'
        ? 'Informe o identificador do modelo Gemini ou deixe vazio para usar o padrão do provedor.'
        : 'O modo heurístico funciona sem um modelo de IA.';
    if (local) loadModels();
  }

  provider.addEventListener('change', updateProvider);
  refresh.addEventListener('click', loadModels);
  updateProvider();
});
