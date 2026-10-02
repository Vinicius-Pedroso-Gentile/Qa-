import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent, type MouseEvent } from 'react';
import type { ModoRecord, Opcao, RecordReply } from '../api';
import { useTelaAoVivo } from '../useTelaAoVivo';
import { Icone } from './Icone';

export interface Gestos {
  onClique: (x: number, y: number) => Promise<RecordReply | null>;
  onTeclado: (entrada: { texto?: string; tecla?: string }) => void;
  onSelecionar: (valor: string) => void;
  onRolar: (x: number, y: number, dx: number, dy: number) => void;
  onMover: (x: number, y: number) => Promise<unknown>;
}

interface Props extends Gestos {
  /** Avisa o App quando a pagina abre ou fecha -- e so isso que ele precisa saber da tela. */
  onAberto: (aberto: boolean) => void;
  url: string;
  /** URL sendo aberta agora; enquanto nao for null, a janela mostra o loading. */
  abrindo: string | null;
  ocupado: boolean;
  chatAberto: boolean;
  gravando: boolean;
  /** Record pedido sem pagina aberta: comeca assim que a URL abrir. */
  recordAoAbrir: boolean;
  modo: ModoRecord;
  pendentes: number;
  onModo: (modo: ModoRecord) => void;
  onRecord: () => void;
  onPararRecord: () => void;
  onCancelarRecordAoAbrir: () => void;
  onAbrir: (url: string) => void;
  onChat: () => void;
}

/** A janela do browser, ao vivo. Sem pagina aberta, vira a tela de inicio. */
export function Palco(props: Props) {
  const { url, abrindo, gravando, modo, pendentes, onModo, onPararRecord, onAberto } = props;
  // A tela chega ~10 vezes por segundo. Morando aqui, cada quadro redesenha so a
  // janela, e nao o App inteiro com todas as listas do lado.
  const src = useTelaAoVivo();
  const aberto = src !== null;
  useEffect(() => onAberto(aberto), [aberto, onAberto]);
  // Durante a abertura o quadro pode ser o about:blank de antes da navegacao; o
  // loading fica na frente ate a pagina de verdade chegar.
  const mostrarTela = src !== null && abrindo === null;

  return (
    <section className={'painel janela' + (gravando && mostrarTela ? ' gravando' : '')}>
      <div className="janela-barra">
        <span className="luzes" aria-hidden="true"><i /><i /><i /></span>
        <div className="endereco">
          <Icone nome="globo" tamanho={13} />
          <span>{abrindo ?? (src ? url || 'carregando…' : 'nenhuma página aberta')}</span>
        </div>
        {mostrarTela && gravando ? (
          <div className="barra-record">
            <span className="rec-selo">gravando</span>
            <div className="segmentos" role="radiogroup" aria-label="Modo do record">
              <button type="button" role="radio" aria-checked={modo === 'interagir'} onClick={() => onModo('interagir')}
                title="Clicar e digitar na página">
                <Icone nome="cursor" tamanho={13} /> Interagir
              </button>
              <button type="button" role="radio" aria-checked={modo === 'validar'} onClick={() => onModo('validar')}
                title="Clicar num texto para validar que ele aparece">
                <Icone nome="texto" tamanho={13} /> Validar texto
              </button>
            </div>
            {pendentes > 0 && <span className="girando" title="Executando no browser…" />}
            <button type="button" className="btn pequeno parar" onClick={onPararRecord}>
              <Icone nome="parar" tamanho={11} /> Parar
            </button>
          </div>
        ) : (
          mostrarTela && <span className="ao-vivo">ao vivo</span>
        )}
      </div>

      <div className="janela-corpo">
        {abrindo !== null && <div className="progresso" aria-hidden="true" />}
        {mostrarTela ? (
          gravando ? (
            <TelaGravavel {...props} src={src} />
          ) : (
            <img src={src ?? undefined} alt="Tela atual do browser controlado pelo agente" />
          )
        ) : abrindo !== null ? (
          <Carregando url={abrindo} />
        ) : (
          <Inicio {...props} />
        )}
      </div>
    </section>
  );
}

// ---------- record: a tela vira interativa ----------

// Teclas que vao como tecla (e nao como texto digitado) para o Playwright.
const ESPECIAIS = new Set([
  'Enter', 'Backspace', 'Delete', 'Tab', 'Escape',
  'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End',
]);

interface Marca { id: number; x: number; y: number }
interface Menu { x: number; y: number; opcoes: Opcao[] }

let proximaMarca = 1;

function TelaGravavel({ src, modo, onClique, onTeclado, onSelecionar, onRolar, onMover }: Gestos & { src: string | null; modo: ModoRecord }) {
  const caixaRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [focado, setFocado] = useState(false);
  const [marcas, setMarcas] = useState<Marca[]>([]);
  const [menu, setMenu] = useState<Menu | null>(null);
  const buffer = useRef('');
  const timer = useRef<number | undefined>(undefined);
  const onRolarRef = useRef(onRolar);
  onRolarRef.current = onRolar;
  const movendo = useRef(false);
  const ultimoMovimento = useRef(0);

  // Do ponto na tela para o ponto na pagina (1280x800). A imagem e desenhada com
  // object-fit: contain, entao pode haver faixa vazia dos lados: ela e descontada.
  function paraPagina(clientX: number, clientY: number) {
    const img = imgRef.current;
    const caixa = caixaRef.current;
    if (!img || !caixa) return null;
    const r = img.getBoundingClientRect();
    const nw = img.naturalWidth || 1280;
    const nh = img.naturalHeight || 800;
    const escala = Math.min(r.width / nw, r.height / nh);
    const x = (clientX - r.left - (r.width - nw * escala) / 2) / escala;
    const y = (clientY - r.top - (r.height - nh * escala) / 2) / escala;
    if (x < 0 || y < 0 || x > nw || y > nh) return null;
    const c = caixa.getBoundingClientRect();
    return { x, y, tx: clientX - c.left, ty: clientY - c.top, largura: c.width, altura: c.height };
  }

  // Letras digitadas em sequencia vao juntas, em lotes de no maximo 40ms. Antes o lote
  // so saia depois de 50ms SEM tecla -- quem digita continuo nunca para tanto, entao o
  // e-mail inteiro ia de uma vez no fim e nada aparecia na tela enquanto se digitava.
  function descarregar() {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    if (buffer.current) {
      const texto = buffer.current;
      buffer.current = '';
      onTeclado({ texto });
    }
  }

  async function clique(e: MouseEvent<HTMLDivElement>) {
    const p = paraPagina(e.clientX, e.clientY);
    if (!p) return;
    descarregar();
    setMenu(null);
    const marca = { id: proximaMarca++, x: p.tx, y: p.ty };
    setMarcas((m) => [...m, marca]);
    window.setTimeout(() => setMarcas((m) => m.filter((x) => x.id !== marca.id)), 650);

    const resposta = await onClique(p.x, p.y);
    if (resposta?.opcoes.length) {
      setMenu({
        x: Math.min(p.tx, p.largura - 230),
        y: Math.min(p.ty, p.altura - 40 - Math.min(resposta.opcoes.length, 8) * 34),
        opcoes: resposta.opcoes,
      });
    }
  }

  function teclas(e: KeyboardEvent<HTMLDivElement>) {
    if (e.nativeEvent.isComposing) return;
    if (menu && e.key === 'Escape') {
      e.preventDefault();
      setMenu(null);
      return;
    }
    // No Windows o AltGr chega como Ctrl+Alt -- e e com ele que se digita o @ num
    // teclado ABNT. Tratar isso como atalho quebraria qualquer e-mail.
    const altGr = e.ctrlKey && e.altKey;
    const atalho = (e.ctrlKey || e.metaKey) && !altGr;

    if (e.key.length === 1 && !atalho) {
      e.preventDefault();
      buffer.current += e.key;
      if (timer.current === undefined) timer.current = window.setTimeout(descarregar, 40);
      return;
    }
    if (ESPECIAIS.has(e.key)) {
      e.preventDefault();
      descarregar();
      onTeclado({ tecla: e.key === 'Tab' && e.shiftKey ? 'Shift+Tab' : e.key });
      return;
    }
    // Ctrl+V fica para o evento de colar; Ctrl+C nao muda nada na pagina.
    if (atalho && e.key.length === 1 && !'vc'.includes(e.key.toLowerCase())) {
      e.preventDefault();
      descarregar();
      onTeclado({ tecla: 'Control+' + e.key.toLowerCase() });
    }
  }

  // Hover: no maximo um movimento a cada 60ms, e nunca dois no ar ao mesmo tempo --
  // mais que isso so enfileira posicoes velhas.
  function mover(e: MouseEvent<HTMLDivElement>) {
    const agora = performance.now();
    if (movendo.current || agora - ultimoMovimento.current < 60) return;
    const p = paraPagina(e.clientX, e.clientY);
    if (!p) return;
    movendo.current = true;
    ultimoMovimento.current = agora;
    onMover(p.x, p.y).finally(() => {
      movendo.current = false;
    });
  }

  function colar(e: ClipboardEvent<HTMLDivElement>) {
    e.preventDefault();
    const texto = e.clipboardData.getData('text');
    if (texto) {
      descarregar();
      onTeclado({ texto });
    }
  }

  // Rolagem: listener nativo porque o do React e passivo e nao consegue impedir a
  // pagina de fora de rolar junto. As deltas de um gesto sao somadas e vao juntas.
  useEffect(() => {
    const caixa = caixaRef.current;
    if (!caixa) return;
    const acumulado = { dx: 0, dy: 0, x: 0, y: 0, timer: undefined as number | undefined };
    function roda(e: WheelEvent) {
      e.preventDefault();
      const p = paraPagina(e.clientX, e.clientY);
      if (!p) return;
      acumulado.dx += e.deltaX;
      acumulado.dy += e.deltaY;
      acumulado.x = p.x;
      acumulado.y = p.y;
      if (acumulado.timer === undefined) {
        acumulado.timer = window.setTimeout(() => {
          const { x, y, dx, dy } = acumulado;
          acumulado.dx = acumulado.dy = 0;
          acumulado.timer = undefined;
          onRolarRef.current(x, y, dx, dy);
        }, 90);
      }
    }
    caixa.addEventListener('wheel', roda, { passive: false });
    return () => {
      caixa.removeEventListener('wheel', roda);
      window.clearTimeout(acumulado.timer);
    };
  }, []);

  // Ao sair do record com letras no buffer, elas ainda vao.
  useEffect(() => () => descarregar(), []);

  return (
    <div
      ref={caixaRef}
      className={`captura modo-${modo}${focado ? ' focado' : ''}`}
      tabIndex={0}
      onClick={clique}
      onMouseMove={mover}
      onKeyDown={teclas}
      onPaste={colar}
      onFocus={() => setFocado(true)}
      onBlur={() => {
        setFocado(false);
        descarregar();
      }}
      aria-label="Tela do browser: clique e digite para gravar"
    >
      <img ref={imgRef} src={src ?? undefined} alt="Tela atual do browser, em gravação" draggable={false} />
      {marcas.map((m) => (
        <span key={m.id} className="marca-clique" style={{ left: m.x, top: m.y }} />
      ))}
      {menu && (
        <div className="menu-opcoes" style={{ left: Math.max(8, menu.x), top: Math.max(8, menu.y) }}
          onClick={(e) => e.stopPropagation()} role="listbox" aria-label="Opções da lista">
          {menu.opcoes.map((o) => (
            <button key={o.valor} type="button" role="option" aria-selected={false}
              onClick={() => {
                setMenu(null);
                onSelecionar(o.valor);
              }}>
              {o.texto || o.valor}
            </button>
          ))}
        </div>
      )}
      <div className="dica-record">
        <Icone nome={modo === 'validar' ? 'texto' : 'teclado'} tamanho={13} />
        {modo === 'validar'
          ? 'Clique no texto que deve aparecer na tela'
          : focado ? 'Teclado ligado à página' : 'Clique na tela para interagir'}
      </div>
    </div>
  );
}

// ---------- abrindo e inicio ----------

function Carregando({ url }: { url: string }) {
  return (
    <div className="carregando" role="status">
      <span className="girando grande" aria-hidden="true" />
      <strong>Abrindo a página…</strong>
      <code>{url}</code>
      <p>Na primeira vez o Playwright ainda precisa iniciar o Chromium — leva alguns segundos.</p>
    </div>
  );
}

// Mesma regra do servidor (literals.find_url): dominio sem esquema ganha https://.
// Aqui ela so serve para avisar o erro antes da viagem ao servidor.
function normalizarUrl(texto: string): string | null {
  const bruto = texto.trim();
  if (!bruto) return null;
  const local = /^(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(bruto);
  const completo = /^https?:\/\//i.test(bruto) ? bruto : (local ? 'http://' : 'https://') + bruto;
  try {
    const u = new URL(completo);
    if (!u.hostname.includes('.') && u.hostname !== 'localhost') return null;
    return u.href;
  } catch {
    return null;
  }
}

function Inicio({ ocupado, chatAberto, recordAoAbrir, onAbrir, onChat, onRecord, onCancelarRecordAoAbrir }: Props) {
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState('');
  const campoRef = useRef<HTMLInputElement>(null);

  function abrir(e: FormEvent) {
    e.preventDefault();
    const url = normalizarUrl(texto);
    if (!url) {
      setErro('Isso não parece uma URL. Exemplo: https://bugbank.netlify.app/');
      return;
    }
    setErro('');
    onAbrir(url);
  }

  function gravar() {
    onRecord();
    const url = normalizarUrl(texto);
    if (url) onAbrir(url);
    else campoRef.current?.focus();
  }

  return (
    <div className="inicio">
      <h2>Qual página você quer testar?</h2>
      <p>Ela abre aqui mesmo, ao vivo, num browser controlado pelo Playwright.</p>

      <form className="abrir-url" onSubmit={abrir}>
        <div className={'abrir-campo' + (erro ? ' invalido' : '')}>
          <Icone nome="globo" tamanho={16} />
          <input
            ref={campoRef}
            value={texto}
            onChange={(e) => {
              setTexto(e.target.value);
              setErro('');
            }}
            placeholder="https://bugbank.netlify.app/"
            aria-label="URL da página"
            aria-invalid={erro ? true : undefined}
            autoFocus
            spellCheck={false}
            autoComplete="url"
            inputMode="url"
          />
        </div>
        <button type="submit" className={'btn ' + (recordAoAbrir ? 'gravar' : 'primario')} disabled={ocupado || !texto.trim()}>
          {recordAoAbrir && <Icone nome="record" tamanho={10} />}
          {recordAoAbrir ? 'Abrir e gravar' : 'Abrir'}
          <Icone nome="seta" tamanho={14} />
        </button>
      </form>
      {erro && <p className="abrir-erro">{erro}</p>}
      {recordAoAbrir && !erro && (
        <p className="aviso-record">
          <span className="ponto-rec" /> A gravação começa assim que a página abrir.
          <button type="button" onClick={onCancelarRecordAoAbrir}>cancelar</button>
        </p>
      )}

      <div className="separador"><span>depois, monte o teste</span></div>

      <div className="opcoes">
        <button type="button" className="opcao" onClick={onChat}>
          <span className="opcao-icone"><Icone nome="chat" tamanho={20} /></span>
          <strong>Conversar com o agente</strong>
          <span>
            Escreva em português — preencher, clicar, validar. O agente executa na hora e
            grava cada passo que der certo.
          </span>
          <em>
            {chatAberto ? 'Chat aberto' : 'Abrir o chat'}
            <Icone nome="seta" tamanho={14} />
          </em>
        </button>

        <button type="button" className="opcao" onClick={gravar}>
          <span className="opcao-icone rec"><Icone nome="record" tamanho={16} /></span>
          <strong>Record</strong>
          <span>
            Clique e digite na própria tela. Cada ação vira um passo, com um seletor
            testado na página naquele instante.
          </span>
          <em>
            {recordAoAbrir ? 'Aguardando a URL' : 'Gravar'}
            <Icone nome="seta" tamanho={14} />
          </em>
        </button>
      </div>
    </div>
  );
}
