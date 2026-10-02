// A mesma regra do servidor (textutil.slugify): e o slug que decide se dois nomes
// sao o mesmo arquivo. "Login" e "login " sao o mesmo bloco; o aviso tem que saber.
export function chave(nome: string): string {
  return nome
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/** "preencher: Informe seu e-mail" -> "Informe seu e-mail" (a acao ja vai no selo). */
export function alvoDoRotulo(rotulo: string): string {
  const i = rotulo.indexOf(': ');
  return i >= 0 ? rotulo.slice(i + 2) : '';
}
