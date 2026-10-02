import { useState } from 'react';
import type { Reply, TesteSalvo } from '../api';
import { Icone } from './Icone';

export interface Execucao {
  ok: boolean;
  passos: Reply[];
  quando: Date;
}

interface Props {
  testes: TesteSalvo[];
  execucoes: Record<string, Execucao>;
  rodando: string | null;
  ocupado: boolean;
  onRodar: (teste: TesteSalvo) => void;
  onExcluir: (teste: TesteSalvo) => void;
}

function formatarData(iso: string): string {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

/** Testes congelados em testes/*.json. Rodar repete os seletores sem chamar a LLM. */
export function TestesSalvos({ testes, execucoes, rodando, ocupado, onRodar, onExcluir }: Props) {
  const [aberto, setAberto] = useState<string | null>(null);

  return (
    <section className="painel lado">
      <header className="lado-topo">
        <h2>Testes salvos</h2>
        <span className="contador">{testes.length}</span>
      </header>

      {!testes.length && <p className="vazio">Nenhum teste salvo ainda.</p>}

      <ul className="testes">
        {testes.map((teste) => {
          const execucao = execucoes[teste.slug];
          const falhas = execucao ? execucao.passos.filter((p) => !p.ok).length : 0;
          const expandido = aberto === teste.slug && execucao;
          return (
            <li key={teste.slug} className={expandido ? 'expandido' : undefined}>
              <div className="teste-linha">
                <button
                  type="button"
                  className="teste-info"
                  onClick={() => setAberto(expandido ? null : teste.slug)}
                  disabled={!execucao}
                  title={execucao ? 'Ver o resultado da última execução' : teste.nome}
                >
                  <span className="teste-nome">{teste.nome}</span>
                  <span className="teste-meta">
                    {teste.passos} passo(s)
                    {teste.blocos > 0 && ` · ${teste.blocos} bloco(s)`} · {formatarData(teste.criado_em)}
                  </span>
                </button>
                {execucao && (
                  <span className={'resultado ' + (execucao.ok ? 'ok' : 'fail')}>
                    {execucao.ok ? 'aprovado' : `${falhas} falha(s)`}
                  </span>
                )}
                <button
                  type="button"
                  className="rodar"
                  disabled={ocupado}
                  onClick={() => {
                    setAberto(teste.slug);
                    onRodar(teste);
                  }}
                  aria-label={'Rodar ' + teste.nome}
                >
                  {rodando === teste.slug ? <span className="girando" /> : <Icone nome="play" tamanho={12} />}
                  Rodar
                </button>
                <button
                  type="button"
                  className="icone-btn mini perigo"
                  disabled={ocupado}
                  onClick={() => onExcluir(teste)}
                  aria-label={'Apagar o teste ' + teste.nome}
                  title="Apagar o teste"
                >
                  <Icone nome="lixo" tamanho={13} />
                </button>
              </div>

              {expandido && (
                <ol className="execucao">
                  {expandido.passos.map((p, i) => (
                    <li key={i} className={p.ok ? 'ok' : 'fail'}>
                      <Icone nome={p.ok ? 'check' : 'x'} tamanho={13} />
                      <div>
                        <span>{p.step || p.message}</span>
                        {p.step && !p.ok && <small>{p.message}</small>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
