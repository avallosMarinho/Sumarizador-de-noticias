// Recarrega somente a tela de processamento, que ainda não contém formulário de decisão.
if (document.querySelector('[data-processing="true"]')) {
  window.setTimeout(() => window.location.reload(), 5000);
}
