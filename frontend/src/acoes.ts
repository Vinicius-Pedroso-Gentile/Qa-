// Os valores de Action em qai/models.py, com o nome que o usuario reconhece.
export const ACOES: Record<string, string> = {
  goto: 'navegar',
  fill: 'preencher',
  click: 'clicar',
  expect_text: 'validar',
  locate: 'localizar',
  clear: 'limpar',
  select: 'selecionar',
  press: 'tecla',
};

export function nomeDaAcao(acao: string): string {
  return ACOES[acao] ?? acao;
}
