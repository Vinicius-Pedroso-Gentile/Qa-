import { useState } from 'react';

// O servidor manda PageElement.describe(): `papel "nome" [formulario]`, nome e
// formulario opcionais. Separar as tres partes deixa a lista legivel de relance.
const DESCRICAO = /^(\S+)(?: "(.*)")?(?: \[([^\]]*)\])?$/;

function separar(descricao: string) {
  const m = DESCRICAO.exec(descricao);
  if (!m) return { papel: '', nome: descricao, form: '' };
  return { papel: m[1], nome: m[2] ?? '', form: m[3] ?? '' };
}

// `desatualizado`: durante o record a pagina muda sem ser remapeada (remapear a cada
// clique custava ate 4s); a lista volta a valer quando o record para.
export function Elementos({ elementos, desatualizado = false }: { elementos: string[]; desatualizado?: boolean }) {
  const [filtro, setFiltro] = useState('');
  const termo = filtro.trim().toLowerCase();
  const visiveis = termo ? elementos.filter((e) => e.toLowerCase().includes(termo)) : elementos;

  return (
    <details className="painel lado elementos" open>
      <summary className="lado-topo">
        <h2>Elementos na página</h2>
        <span className="contador">{elementos.length}</span>
      </summary>
      {desatualizado && elementos.length > 0 && (
        <p className="aviso-campo">Durante o record esta lista não acompanha a tela — ela é refeita quando você parar.</p>
      )}

      {!elementos.length ? (
        <p className="vazio">Nenhuma página aberta.</p>
      ) : (
        <>
          {elementos.length > 8 && (
            <input
              className="filtro"
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              placeholder="Filtrar elementos"
              aria-label="Filtrar elementos"
            />
          )}
          <ul className="lista-elementos">
            {visiveis.map((descricao, i) => {
              const { papel, nome, form } = separar(descricao);
              return (
                <li key={i}>
                  {papel && <span className="papel">{papel}</span>}
                  <span className="el-nome">{nome || '—'}</span>
                  {form && <span className="el-form" title={'Formulário: ' + form}>{form}</span>}
                </li>
              );
            })}
            {!visiveis.length && <li className="vazio">Nenhum elemento com “{filtro}”.</li>}
          </ul>
        </>
      )}
    </details>
  );
}
