import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api, type BlocoView, type Gravado, type ModoRecord, type RecordReply, type Reply, type TesteSalvo,
} from './api';
import { Avisos, type Aviso } from './components/Avisos';
import { Blocos } from './components/Blocos';
import { Chat, type Mensagem } from './components/Chat';
import { Elementos } from './components/Elementos';
import { Palco } from './components/Palco';
import { TesteAtual } from './components/TesteAtual';
import { TestesSalvos, type Execucao } from './components/TestesSalvos';
import { Topo } from './components/Topo';

let proximoId = 1;

export function App() {
  // O chat so aparece quando o usuario pede; o historico continua existindo fechado.
  const [chatAberto, setChatAberto] = useState(false);
  const [mensagens, setMensagens] = useState<Mensagem[]>(() => [
    { id: proximoId++, autor: 'bot', texto: 'Para qual URL você quer ir?' },
  ]);
  const [ocupado, setOcupado] = useState(false);
  const [rodando, setRodando] = useState<string | null>(null);
  const [url, setUrl] = useState('');
  const [elementos, setElementos] = useState<string[]>([]);
  const [gravado, setGravado] = useState<Gravado>({ url_inicial: '', itens: [], total_passos: 0 });
  const [testes, setTestes] = useState<TesteSalvo[]>([]);
  const [blocos, setBlocos] = useState<BlocoView[]>([]);
  const [execucoes, setExecucoes] = useState<Record<string, Execucao>>({});
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  // `respondeu`: o servidor ja terminou o goto e so falta o primeiro quadro da pagina.
  const [abrindo, setAbrindo] = useState<{ url: string; respondeu: boolean } | null>(null);
  const [gravando, setGravando] = useState(false);
  const [recordAoAbrir, setRecordAoAbrirEstado] = useState(false);
  // Espelho em ref: o card "Record" pede a gravacao e abre a URL no mesmo clique, e o
  // abrirUrl daquele clique ainda enxergaria o estado antigo.
  const recordAoAbrirRef = useRef(false);
  const setRecordAoAbrir = useCallback((valor: boolean) => {
    recordAoAbrirRef.current = valor;
    setRecordAoAbrirEstado(valor);
  }, []);
  const [modo, setModo] = useState<ModoRecord>('interagir');
  const [pendentes, setPendentes] = useState(0);
  const timers = useRef(new Map<number, number>());
  // Gestos do record saem em fila: a letra digitada depois do clique no campo nao
  // pode chegar ao servidor antes do clique.
  const fila = useRef<Promise<unknown>>(Promise.resolve());

  // Quem acompanha a tela e o Palco; o App so precisa saber se ha pagina aberta.
  const [browserAberto, setBrowserAberto] = useState(false);

  useEffect(() => {
    if (abrindo?.respondeu && browserAberto) setAbrindo(null);
  }, [abrindo, browserAberto]);

  // Browser fechado (pelo botao ou porque o servidor reiniciou): nao ha o que gravar.
  useEffect(() => {
    if (!browserAberto && !abrindo) setGravando(false);
  }, [browserAberto, abrindo]);

  const fecharAviso = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setAvisos((lista) => lista.filter((a) => a.id !== id));
  }, []);

  const avisar = useCallback(
    (texto: string, tipo: Aviso['tipo'] = 'info') => {
      const id = proximoId++;
      // O mesmo aviso ja na tela nao se repete: digitar sem campo em foco manda um
      // aviso por lote de teclas, e seriam dez caixas iguais empilhadas.
      setAvisos((lista) => (lista.some((a) => a.texto === texto)
        ? lista
        : [...lista.slice(-3), { id, texto, tipo }]));
      timers.current.set(id, window.setTimeout(() => fecharAviso(id), 4500));
    },
    [fecharAviso],
  );

  function escrever(...novas: Omit<Mensagem, 'id'>[]) {
    const comId = novas.map((m) => ({ ...m, id: proximoId++ }));
    setMensagens((lista) => [...lista, ...comId]);
    return comId.map((m) => m.id);
  }

  function tirar(id: number) {
    setMensagens((lista) => lista.filter((m) => m.id !== id));
  }

  function aplicarEstado(resposta: Pick<Reply, 'url' | 'elements'>) {
    setUrl(resposta.url || '');
    setElementos(resposta.elements || []);
  }

  const recarregarGravacao = useCallback(() => {
    api.gravacao().then(setGravado).catch(() => { /* servidor reiniciando */ });
  }, []);

  const recarregarTestes = useCallback(() => {
    api.testes().then(setTestes).catch(() => { /* servidor reiniciando */ });
  }, []);

  const recarregarBlocos = useCallback(() => {
    api.blocos().then(setBlocos).catch(() => { /* servidor reiniciando */ });
  }, []);

  useEffect(() => {
    api.estado().then(aplicarEstado).catch(() => {
      avisar('Não consegui falar com o servidor. Ele está rodando?', 'fail');
    });
    recarregarGravacao();
    recarregarTestes();
    recarregarBlocos();
  }, [avisar, recarregarGravacao, recarregarTestes, recarregarBlocos]);

  // A resposta tem o mesmo formato no chat e no replay de um teste salvo.
  function mostrarPassos(passos: Reply[]) {
    escrever(
      ...passos.map((p): Omit<Mensagem, 'id'> => ({
        autor: 'bot',
        texto: p.message,
        estado: p.ok ? 'ok' : 'fail',
        acao: p.action || undefined,
        passo: p.step || undefined,
        codigo: p.selector_code || undefined,
      })),
    );
    if (passos.length) aplicarEstado(passos[passos.length - 1]);
  }

  async function enviarComando(texto: string) {
    setOcupado(true);
    const [, pensando] = escrever(
      { autor: 'user', texto },
      { autor: 'bot', texto: 'O agente está trabalhando…', estado: 'pensando' },
    );
    try {
      const passos = await api.comando(texto);
      tirar(pensando);
      mostrarPassos(passos);
    } catch (erro) {
      tirar(pensando);
      escrever({ autor: 'bot', texto: 'Não consegui falar com o servidor: ' + String(erro), estado: 'fail' });
    } finally {
      setOcupado(false);
      recarregarGravacao();
    }
  }

  // O campo da tela inicial: a URL vai direto para o Playwright, sem LLM.
  async function abrirUrl(endereco: string) {
    setOcupado(true);
    setAbrindo({ url: endereco, respondeu: false });
    escrever({ autor: 'user', texto: endereco });
    try {
      const resposta = await api.abrir(endereco);
      mostrarPassos([resposta]);
      if (resposta.ok) {
        setAbrindo({ url: endereco, respondeu: true });
        // Rede de seguranca: se o quadro nao vier, o loading nao fica preso para sempre.
        window.setTimeout(() => setAbrindo((atual) => (atual?.url === endereco ? null : atual)), 5000);
        if (recordAoAbrirRef.current) {
          setRecordAoAbrir(false);
          setGravando(true);
        }
      } else {
        setAbrindo(null);
        avisar(resposta.message, 'fail');
      }
    } catch (erro) {
      setAbrindo(null);
      escrever({ autor: 'bot', texto: 'Não consegui falar com o servidor: ' + String(erro), estado: 'fail' });
      avisar('Não consegui abrir a página.', 'fail');
    } finally {
      setOcupado(false);
      recarregarGravacao();
    }
  }

  // ---------- record ----------

  function alternarRecord() {
    if (gravando) {
      setGravando(false);
      setModo('interagir');
      // O record nao remapeia a pagina a cada gesto; ao parar, a lista de elementos
      // volta a refletir a tela.
      void naFila(() => api.inventario()).then((r) => r.ok && aplicarEstado(r)).catch(() => undefined);
      return;
    }
    if (browserAberto) {
      setGravando(true);
      return;
    }
    // Sem pagina, nao ha onde clicar: o record espera a URL abrir.
    setRecordAoAbrir(true);
    avisar('Digite a URL da página — a gravação começa assim que ela abrir.');
  }

  function naFila<T>(chamada: () => Promise<T>): Promise<T> {
    const vez = fila.current.then(chamada, chamada);
    fila.current = vez.catch(() => undefined);
    return vez;
  }

  async function gesto(chamada: () => Promise<RecordReply>, avisarSemGravar = false): Promise<RecordReply | null> {
    setPendentes((n) => n + 1);
    try {
      const resposta = await naFila(chamada);
      aplicarEstado(resposta);
      if (!resposta.ok) avisar(resposta.message, 'fail');
      else if (resposta.aviso) avisar(resposta.aviso, 'fail');
      else if (avisarSemGravar && !resposta.gravado && !resposta.opcoes.length && resposta.message) {
        avisar(resposta.message);
      }
      if (resposta.gravado) recarregarGravacao();
      return resposta;
    } catch (erro) {
      avisar('O record falhou: ' + String(erro), 'fail');
      return null;
    } finally {
      setPendentes((n) => n - 1);
    }
  }

  const gestos = {
    onClique: (x: number, y: number) => gesto(() => api.record.clique(x, y, modo), true),
    onTeclado: (entrada: { texto?: string; tecla?: string }) => {
      void gesto(() => api.record.teclado(entrada));
    },
    onSelecionar: (valor: string) => {
      void gesto(() => api.record.selecionar(valor));
    },
    onRolar: (x: number, y: number, dx: number, dy: number) => {
      void gesto(() => api.record.rolar(x, y, dx, dy));
    },
    // Hover fica fora da fila: e so posicao do mouse, e atrasa-lo atras de um clique
    // faria o menu abrir depois da hora.
    onMover: (x: number, y: number) => api.record.mover(x, y).catch(() => undefined),
  };

  // ---------- teste em construcao e blocos ----------

  // Toda edicao responde com um Reply; o que muda e so a chamada.
  async function editarGravacao(chamada: () => Promise<Reply>, avisarOk = false): Promise<boolean> {
    try {
      const resposta = await chamada();
      if (!resposta.ok) avisar(resposta.message, 'fail');
      else if (avisarOk) avisar(resposta.message, 'ok');
      return resposta.ok;
    } catch (erro) {
      avisar('Não consegui alterar o teste: ' + String(erro), 'fail');
      return false;
    } finally {
      recarregarGravacao();
    }
  }

  async function agrupar(indices: number[], nome: string, substituir: boolean) {
    const ok = await editarGravacao(() => api.agrupar(indices, nome, substituir), true);
    recarregarBlocos();
    return ok;
  }

  async function inserirBloco(bloco: BlocoView) {
    if (await editarGravacao(() => api.inserirBloco(bloco.slug))) {
      avisar(`Bloco "${bloco.nome}" adicionado ao fim do teste.`, 'ok');
    }
  }

  async function excluirBloco(bloco: BlocoView) {
    const aviso = bloco.usado_em.length
      ? `\n\nEle é usado em: ${bloco.usado_em.join(', ')}. Esses testes vão falhar no ponto do bloco.`
      : '';
    if (!window.confirm(`Excluir o bloco "${bloco.nome}"?${aviso}`)) return;
    try {
      const resposta = await api.excluirBloco(bloco.slug);
      avisar(resposta.ok ? `Bloco "${bloco.nome}" excluído.` : resposta.message, resposta.ok ? 'info' : 'fail');
    } catch {
      avisar('Não consegui excluir o bloco.', 'fail');
    }
    recarregarBlocos();
    recarregarGravacao();
  }

  async function rodarTeste(teste: TesteSalvo) {
    setOcupado(true);
    setRodando(teste.slug);
    const [, pensando] = escrever(
      { autor: 'user', texto: `Rodar o teste "${teste.nome}"` },
      {
        autor: 'bot',
        texto: `Executando ${teste.passos} passo(s) — sem LLM, os seletores já estão decididos.`,
        estado: 'pensando',
      },
    );
    try {
      const passos = await api.rodarTeste(teste.slug);
      tirar(pensando);
      mostrarPassos(passos);
      const ok = passos.length > 0 && passos.every((p) => p.ok);
      setExecucoes((atual) => ({ ...atual, [teste.slug]: { ok, passos, quando: new Date() } }));
      const resumo = ok ? 'Teste aprovado — todos os passos passaram.' : 'Teste reprovado.';
      escrever({ autor: 'bot', texto: resumo, estado: ok ? 'ok' : 'fail' });
      avisar(`"${teste.nome}": ${ok ? 'aprovado' : 'reprovado'}`, ok ? 'ok' : 'fail');
    } catch (erro) {
      tirar(pensando);
      escrever({ autor: 'bot', texto: 'Não consegui rodar o teste: ' + String(erro), estado: 'fail' });
      avisar('Não consegui rodar o teste.', 'fail');
    } finally {
      setOcupado(false);
      setRodando(null);
    }
  }

  async function excluirTeste(teste: TesteSalvo) {
    if (!window.confirm(`Apagar o teste "${teste.nome}"?

O arquivo testes/${teste.slug}.json é removido. Os blocos que ele usa continuam existindo.`)) return;
    try {
      const resposta = await api.excluirTeste(teste.slug);
      avisar(resposta.message, resposta.ok ? 'info' : 'fail');
      if (resposta.ok) {
        setExecucoes(({ [teste.slug]: _apagado, ...resto }) => resto);
      }
    } catch {
      avisar('Não consegui apagar o teste.', 'fail');
    }
    recarregarTestes();
    // "usado em N testes" dos blocos muda quando um teste some.
    recarregarBlocos();
  }

  async function salvarTeste(nome: string): Promise<boolean> {
    try {
      const resposta = await api.salvarTeste(nome);
      avisar(resposta.message, resposta.ok ? 'ok' : 'fail');
      recarregarTestes();
      recarregarBlocos();
      return resposta.ok;
    } catch (erro) {
      avisar('Não consegui salvar: ' + String(erro), 'fail');
      return false;
    }
  }

  async function descartar() {
    if (!window.confirm('Descartar o teste em construção?')) return;
    try {
      await api.limparGravacao();
      avisar('Teste em construção descartado. A próxima ação começa um teste novo.');
    } catch {
      avisar('Não consegui descartar a gravação.', 'fail');
    }
    recarregarGravacao();
  }

  async function fecharBrowser() {
    try {
      await api.encerrar();
      setGravando(false);
      aplicarEstado({ url: '', elements: [] });
      escrever({ autor: 'bot', texto: 'Browser fechado. Mande uma URL para começar de novo.' });
      avisar('Browser fechado.');
    } catch {
      avisar('Não consegui fechar o browser.', 'fail');
    }
  }

  return (
    <div className="app">
      <Topo
        url={url}
        browserAberto={browserAberto}
        chatAberto={chatAberto}
        gravando={gravando}
        onChat={() => setChatAberto((aberto) => !aberto)}
        onRecord={alternarRecord}
        onFechar={fecharBrowser}
      />

      <main className={'corpo' + (chatAberto ? ' com-chat' : '')}>
        {chatAberto && (
          <Chat
            mensagens={mensagens}
            ocupado={ocupado}
            onEnviar={enviarComando}
            onFechar={() => setChatAberto(false)}
          />
        )}

        <div className="area">
          <div className="area-grade">
            <Palco
              onAberto={setBrowserAberto}
              url={url}
              abrindo={abrindo?.url ?? null}
              ocupado={ocupado}
              chatAberto={chatAberto}
              gravando={gravando}
              recordAoAbrir={recordAoAbrir}
              modo={modo}
              pendentes={pendentes}
              onModo={setModo}
              onRecord={() => setRecordAoAbrir(true)}
              onPararRecord={alternarRecord}
              onCancelarRecordAoAbrir={() => setRecordAoAbrir(false)}
              onAbrir={abrirUrl}
              onChat={() => setChatAberto(true)}
              {...gestos}
            />
            <div className="lateral">
              <TesteAtual
                gravado={gravado}
                testes={testes}
                blocos={blocos}
                gravando={gravando}
                onSalvar={salvarTeste}
                onDescartar={descartar}
                onRemover={(i) => void editarGravacao(() => api.remover(i))}
                onMover={(i, para) => void editarGravacao(() => api.mover(i, para))}
                onEditar={(i, valor) => editarGravacao(() => api.editar(i, valor))}
                onAgrupar={agrupar}
              />
              <Blocos blocos={blocos} onInserir={inserirBloco} onExcluir={excluirBloco} />
              <TestesSalvos
                testes={testes}
                execucoes={execucoes}
                rodando={rodando}
                ocupado={ocupado}
                onRodar={rodarTeste}
                onExcluir={excluirTeste}
              />
              <Elementos elementos={elementos} desatualizado={gravando} />
            </div>
          </div>
        </div>
      </main>

      <Avisos avisos={avisos} onFechar={fecharAviso} />
    </div>
  );
}
