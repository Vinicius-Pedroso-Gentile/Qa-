import { Icone } from './Icone';

interface Props {
  url: string;
  browserAberto: boolean;
  chatAberto: boolean;
  gravando: boolean;
  onChat: () => void;
  onRecord: () => void;
  onFechar: () => void;
}

export function Topo({ url, browserAberto, chatAberto, gravando, onChat, onRecord, onFechar }: Props) {
  return (
    <header className="topo">
      <div className="marca">
        <span className="logo" aria-hidden="true"><Icone nome="check" tamanho={18} /></span>
        <div>
          <strong>Qaí</strong>
          <small>agente de teste</small>
        </div>
      </div>

      <div className={'status' + (browserAberto ? ' aberto' : '')} title={url || undefined}>
        <span className="ponto" />
        <span className="status-texto">
          {browserAberto ? url || 'Browser aberto' : 'Nenhum browser aberto'}
        </span>
      </div>

      <nav className="acoes">
        <button
          type="button"
          className={'btn' + (chatAberto ? ' ativo' : ' primario')}
          aria-pressed={chatAberto}
          onClick={onChat}
        >
          <Icone nome="chat" />
          {chatAberto ? 'Fechar chat' : 'Usar o chat'}
        </button>
        <button
          type="button"
          className={'btn' + (gravando ? ' gravando' : '')}
          aria-pressed={gravando}
          onClick={onRecord}
          title={gravando ? 'Parar a gravação' : 'Gravar clicando e digitando na página'}
        >
          {gravando ? <Icone nome="parar" tamanho={11} /> : <span className="rec"><Icone nome="record" tamanho={12} /></span>}
          {gravando ? 'Parar record' : 'Record'}
        </button>
        <button
          type="button"
          className="btn fantasma"
          disabled={!browserAberto}
          onClick={onFechar}
          aria-label="Fechar browser"
          title="Fechar browser"
        >
          <Icone nome="power" />
          <span className="btn-texto">Fechar browser</span>
        </button>
      </nav>
    </header>
  );
}
