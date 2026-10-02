export interface Aviso {
  id: number;
  texto: string;
  tipo: 'ok' | 'fail' | 'info';
}

/** Notificacoes curtas: o resultado de uma acao aparece mesmo com o chat fechado. */
export function Avisos({ avisos, onFechar }: { avisos: Aviso[]; onFechar: (id: number) => void }) {
  return (
    <div className="avisos" role="status" aria-live="polite">
      {avisos.map((a) => (
        <button key={a.id} type="button" className={'aviso ' + a.tipo} onClick={() => onFechar(a.id)}>
          {a.texto}
        </button>
      ))}
    </div>
  );
}
