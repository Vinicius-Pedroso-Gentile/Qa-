// Espelho dos modelos Pydantic de qai/server.py. Se um campo mudar la, muda aqui:
// e isto que faz o TypeScript acusar o erro no build, e nao o usuario na tela.

export interface Reply {
  ok: boolean;
  message: string;
  action: string;
  selector_code: string;
  step: string;
  url: string;
  elements: string[];
}

export interface PassoView {
  label: string;
  action: string;
  value: string;
  selector_code: string;
  editavel: boolean;
}

export interface ItemView {
  tipo: 'passo' | 'bloco';
  passo: PassoView | null;
  bloco_slug: string;
  bloco_nome: string;
  bloco_passos: PassoView[];
  bloco_ausente: boolean;
}

export interface Gravado {
  url_inicial: string;
  itens: ItemView[];
  total_passos: number;
}

export interface TesteSalvo {
  slug: string;
  nome: string;
  passos: number;
  blocos: number;
  criado_em: string;
}

export interface BlocoView {
  slug: string;
  nome: string;
  criado_em: string;
  url_inicial: string;
  passos: PassoView[];
  usado_em: string[];
}

export interface Opcao {
  valor: string;
  texto: string;
}

export interface RecordReply {
  ok: boolean;
  message: string;
  gravado: boolean;
  aviso: string;
  selector_code: string;
  opcoes: Opcao[];
  url: string;
  elements: string[];
}

export type ModoRecord = 'interagir' | 'validar';

async function ler<T>(resposta: Response): Promise<T> {
  if (!resposta.ok) throw new Error(`${resposta.status} ${resposta.statusText}`);
  return (await resposta.json()) as T;
}

function get<T>(caminho: string): Promise<T> {
  return fetch(caminho).then((r) => ler<T>(r));
}

function post<T>(caminho: string, corpo?: unknown): Promise<T> {
  return fetch(caminho, {
    method: 'POST',
    headers: corpo === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  }).then((r) => ler<T>(r));
}

export const api = {
  estado: () => get<Reply>('/api/estado'),
  // Uma mensagem pode conter varias ordens; cada uma volta como um Reply.
  comando: (text: string) => post<Reply[]>('/api/comando', { text }),
  // Abre a URL direto no Playwright, sem LLM: e o campo da tela inicial.
  abrir: (url: string) => post<Reply>('/api/abrir', { url }),
  encerrar: () => post<Reply>('/api/encerrar'),

  // Record: gestos na tela embutida, em coordenadas da pagina (1280x800).
  record: {
    clique: (x: number, y: number, modo: ModoRecord) => post<RecordReply>('/api/record/clique', { x, y, modo }),
    teclado: (entrada: { texto?: string; tecla?: string }) => post<RecordReply>('/api/record/teclado', entrada),
    selecionar: (valor: string) => post<RecordReply>('/api/record/selecionar', { valor }),
    rolar: (x: number, y: number, dx: number, dy: number) =>
      post<RecordReply>('/api/record/rolar', { x, y, dx, dy }),
    // Hover: responde 204 sem corpo, entao nao passa pelo `post` que le JSON.
    mover: (x: number, y: number) =>
      fetch('/api/record/mover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x, y }),
      }),
  },
  // O record nao remapeia a pagina a cada gesto; isto refaz o inventario ao parar.
  inventario: () => post<Reply>('/api/inventario'),

  // Teste em construcao: itens por posicao na lista.
  gravacao: () => get<Gravado>('/api/gravacao'),
  limparGravacao: () => post<Reply>('/api/gravacao/limpar'),
  remover: (indice: number) => post<Reply>('/api/gravacao/remover', { indice }),
  mover: (indice: number, para: number) => post<Reply>('/api/gravacao/mover', { indice, para }),
  editar: (indice: number, valor: string) => post<Reply>('/api/gravacao/editar', { indice, valor }),
  inserirBloco: (slug: string) => post<Reply>('/api/gravacao/inserir-bloco', { slug }),
  agrupar: (indices: number[], nome: string, substituir: boolean) =>
    post<Reply>('/api/gravacao/agrupar', { indices, nome, substituir }),

  blocos: () => get<BlocoView[]>('/api/blocos'),
  excluirBloco: (slug: string) => post<Reply>('/api/blocos/excluir', { slug }),

  testes: () => get<TesteSalvo[]>('/api/testes'),
  salvarTeste: (nome: string) => post<Reply>('/api/testes', { nome }),
  rodarTeste: (slug: string) => post<Reply[]>('/api/testes/rodar', { slug }),
  excluirTeste: (slug: string) => post<Reply>('/api/testes/excluir', { slug }),
};
