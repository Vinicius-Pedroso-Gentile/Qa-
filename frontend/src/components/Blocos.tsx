import { useState } from 'react';
import type { BlocoView } from '../api';
import { Icone } from './Icone';
import { ListaDePassos } from './TesteAtual';

interface Props {
  blocos: BlocoView[];
  onInserir: (bloco: BlocoView) => void;
  onExcluir: (bloco: BlocoView) => void;
}

/** A biblioteca de blocos: trechos prontos para entrar em qualquer teste. */
export function Blocos({ blocos, onInserir, onExcluir }: Props) {
  const [aberto, setAberto] = useState<string | null>(null);

  return (
    <section className="painel lado">
      <header className="lado-topo">
        <h2>Blocos</h2>
        <span className="contador">{blocos.length}</span>
      </header>

      {!blocos.length && (
        <p className="vazio">
          Marque passos no teste em construção e crie um bloco — “Login”, por exemplo.
          Depois ele entra em qualquer teste com um clique.
        </p>
      )}

      <ul className="testes">
        {blocos.map((b) => (
          <li key={b.slug}>
            <div className="teste-linha">
              <button
                type="button"
                className="teste-info"
                onClick={() => setAberto(aberto === b.slug ? null : b.slug)}
                aria-expanded={aberto === b.slug}
                title="Ver os passos do bloco"
              >
                <span className="teste-nome"><Icone nome="bloco" tamanho={12} /> {b.nome}</span>
                <span className="teste-meta">
                  {b.passos.length} passo(s) ·{' '}
                  {b.usado_em.length ? `usado em ${b.usado_em.length} teste(s)` : 'ainda não usado'}
                </span>
              </button>
              <button type="button" className="btn pequeno" onClick={() => onInserir(b)}
                title="Adicionar ao fim do teste em construção">
                <Icone nome="mais" tamanho={13} /> Usar
              </button>
              <button type="button" className="icone-btn mini perigo" onClick={() => onExcluir(b)}
                aria-label={'Excluir o bloco ' + b.nome} title="Excluir o bloco">
                <Icone nome="lixo" tamanho={13} />
              </button>
            </div>
            {aberto === b.slug && (
              <div className="bloco-detalhe">
                <ListaDePassos passos={b.passos} />
                {b.usado_em.length > 0 && <p className="teste-meta">Usado em: {b.usado_em.join(', ')}</p>}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
