import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { nomeDaAcao } from '../acoes';
import { Icone } from './Icone';

export interface Mensagem {
  id: number;
  autor: 'user' | 'bot';
  texto: string;
  estado?: 'ok' | 'fail' | 'pensando';
  acao?: string;
  passo?: string;
  codigo?: string;
}

const EXEMPLOS = [
  'https://bugbank.netlify.app/',
  'Localizar o campo E-mail',
  'Informar o e-mail qualquerCoisa0001@gmail.com',
  'Informar a senha Teste@123',
  'Clicar no botão Acessar',
  'Validar que aparece a mensagem: "Usuário ou senha inválido. Tente novamente ou verifique suas informações!"',
  'informe o e-mail qualquerCoisa0001@gmail.com, informe a senha Teste@123, clique em Acessar e valide que aparece a mensagem: "Usuário ou senha inválido. Tente novamente ou verifique suas informações!"',
];

interface Props {
  mensagens: Mensagem[];
  ocupado: boolean;
  onEnviar: (texto: string) => void;
  onFechar: () => void;
}

export function Chat({ mensagens, ocupado, onEnviar, onFechar }: Props) {
  const [rascunho, setRascunho] = useState('');
  const [posHistorico, setPosHistorico] = useState<number | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const campoRef = useRef<HTMLTextAreaElement>(null);

  const historico = mensagens.filter((m) => m.autor === 'user').map((m) => m.texto);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [mensagens]);

  useEffect(() => {
    campoRef.current?.focus();
  }, []);

  // A caixa cresce com o texto: um cenario inteiro numa mensagem so tem varias linhas.
  useEffect(() => {
    const campo = campoRef.current;
    if (!campo) return;
    campo.style.height = 'auto';
    campo.style.height = campo.scrollHeight + 'px';
  }, [rascunho]);

  function enviar(e?: FormEvent) {
    e?.preventDefault();
    const texto = rascunho.trim();
    if (!texto || ocupado) return;
    onEnviar(texto);
    setRascunho('');
    setPosHistorico(null);
  }

  function usarExemplo(exemplo: string) {
    setRascunho(exemplo);
    campoRef.current?.focus();
  }

  function teclas(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      enviar();
      return;
    }
    // Seta para cima/baixo percorre os comandos ja mandados, como num terminal. So
    // quando o cursor esta no inicio, para nao roubar a navegacao dentro do texto.
    const campo = e.currentTarget;
    if (e.key === 'ArrowUp' && campo.selectionStart === 0 && historico.length) {
      e.preventDefault();
      const pos = posHistorico === null ? historico.length - 1 : Math.max(0, posHistorico - 1);
      setPosHistorico(pos);
      setRascunho(historico[pos]);
    } else if (e.key === 'ArrowDown' && posHistorico !== null) {
      e.preventDefault();
      const pos = posHistorico + 1;
      if (pos >= historico.length) {
        setPosHistorico(null);
        setRascunho('');
      } else {
        setPosHistorico(pos);
        setRascunho(historico[pos]);
      }
    }
  }

  return (
    <section className="painel chat" aria-label="Chat com o agente">
      <header className="chat-topo">
        <div>
          <h2>Chat com o agente</h2>
          <p>Várias ordens na mesma mensagem viram vários passos.</p>
        </div>
        <button type="button" className="icone-btn" onClick={onFechar} aria-label="Fechar o chat">
          <Icone nome="x" />
        </button>
      </header>

      <div className="log" ref={logRef} aria-live="polite">
        {mensagens.map((m) => (
          <Bolha key={m.id} mensagem={m} />
        ))}
      </div>

      <details className="exemplos">
        <summary>Exemplos de comando</summary>
        <div className="chips">
          {EXEMPLOS.map((exemplo) => (
            <button key={exemplo} type="button" title={exemplo} onClick={() => usarExemplo(exemplo)}>
              {exemplo.length > 120
                ? '▶ cenário inteiro de uma vez'
                : exemplo.length > 38
                  ? exemplo.slice(0, 36) + '…'
                  : exemplo}
            </button>
          ))}
        </div>
      </details>

      <form className="entrada" onSubmit={enviar}>
        <textarea
          ref={campoRef}
          rows={1}
          value={rascunho}
          onChange={(e) => {
            setRascunho(e.target.value);
            setPosHistorico(null);
          }}
          onKeyDown={teclas}
          placeholder="Digite um comando ou uma URL…"
          aria-label="Comando"
        />
        <button type="submit" className="enviar" disabled={ocupado || !rascunho.trim()} aria-label="Enviar">
          <Icone nome="enviar" />
        </button>
      </form>
      <p className="dica">Enter envia · Shift+Enter quebra linha · ↑ repete o último comando</p>
    </section>
  );
}

function Bolha({ mensagem }: { mensagem: Mensagem }) {
  const { autor, texto, estado, acao, passo, codigo } = mensagem;

  if (estado === 'pensando') {
    return (
      <div className="msg bot pensando">
        <span className="pontinhos" aria-hidden="true"><i /><i /><i /></span>
        {texto}
      </div>
    );
  }

  return (
    <div className={`msg ${autor}${estado ? ' ' + estado : ''}`}>
      {(acao || passo) && (
        <div className="msg-cabeca">
          {acao && <span className={'acao acao-' + acao}>{nomeDaAcao(acao)}</span>}
          {passo && <span className="passo">{passo}</span>}
        </div>
      )}
      <div className="msg-texto">{texto}</div>
      {codigo && <Codigo codigo={codigo} />}
    </div>
  );
}

function Codigo({ codigo }: { codigo: string }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(codigo);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1500);
    } catch {
      // sem permissao de clipboard: o texto continua selecionavel na tela
    }
  }

  return (
    <div className="codigo">
      <code>{codigo}</code>
      <button type="button" onClick={copiar} aria-label="Copiar o seletor" title="Copiar">
        <Icone nome={copiado ? 'check' : 'copiar'} tamanho={13} />
      </button>
    </div>
  );
}
