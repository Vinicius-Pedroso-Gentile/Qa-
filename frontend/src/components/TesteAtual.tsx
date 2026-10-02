import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { BlocoView, Gravado, ItemView, PassoView, TesteSalvo } from '../api';
import { nomeDaAcao } from '../acoes';
import { alvoDoRotulo, chave } from '../chave';
import { Icone } from './Icone';

interface Props {
  gravado: Gravado;
  testes: TesteSalvo[];
  blocos: BlocoView[];
  gravando: boolean;
  onSalvar: (nome: string) => Promise<boolean>;
  onDescartar: () => void;
  onRemover: (indice: number) => void;
  onMover: (indice: number, para: number) => void;
  onEditar: (indice: number, valor: string) => Promise<boolean>;
  onAgrupar: (indices: number[], nome: string, substituir: boolean) => Promise<boolean>;
}

// Nestas acoes o rotulo mostra o elemento, entao o valor vai numa linha propria.
const VALOR_A_PARTE = new Set(['fill', 'select', 'press']);

/**
 * O teste que esta sendo montado: passos (do chat ou do record) e blocos.
 *
 * Aqui o teste e corrigido antes de salvar -- tirar um clique a mais, trocar a ordem,
 * ajustar um valor -- e trechos viram blocos reutilizaveis.
 */
export function TesteAtual(props: Props) {
  const { gravado, testes, blocos, gravando, onSalvar, onDescartar, onRemover, onMover, onEditar, onAgrupar } = props;
  const itens = gravado.itens;

  const [nome, setNome] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [nomeBloco, setNomeBloco] = useState('');
  const [expandidos, setExpandidos] = useState<Set<number>>(new Set());
  const [editando, setEditando] = useState<{ indice: number; valor: string } | null>(null);
  const [novo, setNovo] = useState<number | null>(null);
  const listaRef = useRef<HTMLOListElement>(null);
  const tamanhoAnterior = useRef(itens.length);

  // Os indices valem para a lista de agora; se ela mudou de tamanho, a selecao e a
  // edicao em andamento apontariam para outro item.
  useEffect(() => {
    const cresceu = itens.length > tamanhoAnterior.current;
    if (itens.length !== tamanhoAnterior.current) {
      setSelecionados(new Set());
      setExpandidos(new Set());
      setEditando(null);
    }
    tamanhoAnterior.current = itens.length;
    if (cresceu) {
      // O passo que acabou de entrar pisca, e a lista rola ate ele.
      setNovo(itens.length - 1);
      const lista = listaRef.current;
      if (lista) lista.scrollTop = lista.scrollHeight;
      const t = window.setTimeout(() => setNovo(null), 1400);
      return () => window.clearTimeout(t);
    }
  }, [itens.length]);

  const testeExistente = testes.some((t) => chave(t.nome) === chave(nome) && nome.trim());
  const blocoExistente = nomeBloco.trim() ? blocos.find((b) => b.slug === chave(nomeBloco)) : undefined;

  function alternar(conjunto: Set<number>, i: number) {
    const novoConjunto = new Set(conjunto);
    if (novoConjunto.has(i)) novoConjunto.delete(i);
    else novoConjunto.add(i);
    return novoConjunto;
  }

  function mover(i: number, para: number) {
    setSelecionados(new Set());
    setExpandidos(new Set());
    onMover(i, para);
  }

  async function salvarTeste(e: FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !itens.length || salvando) return;
    setSalvando(true);
    if (await onSalvar(nome.trim())) setNome('');
    setSalvando(false);
  }

  async function criarBloco(e: FormEvent) {
    e.preventDefault();
    if (!nomeBloco.trim() || !selecionados.size) return;
    if (await onAgrupar([...selecionados], nomeBloco.trim(), Boolean(blocoExistente))) {
      setNomeBloco('');
      setSelecionados(new Set());
    }
  }

  async function confirmarEdicao(e: FormEvent) {
    e.preventDefault();
    if (!editando) return;
    if (await onEditar(editando.indice, editando.valor)) setEditando(null);
  }

  return (
    <section className="painel lado construcao">
      <header className="lado-topo">
        <h2>Teste em construção</h2>
        <span className="contador" title="Passos, contando os de dentro dos blocos">{gravado.total_passos}</span>
        {gravando && <span className="rec-mini">gravando</span>}
        <button
          type="button"
          className="icone-btn pequeno empurra"
          disabled={!itens.length}
          onClick={onDescartar}
          title="Descartar tudo"
          aria-label="Descartar o teste em construção"
        >
          <Icone nome="lixo" tamanho={14} />
        </button>
      </header>

      {itens.length ? (
        <ol className="itens" ref={listaRef}>
          {itens.map((item, i) => (
            <li
              key={i}
              className={
                'item' + (item.tipo === 'bloco' ? ' item-bloco' : '')
                + (selecionados.has(i) ? ' selecionado' : '') + (novo === i ? ' novo' : '')
              }
            >
              {item.tipo === 'passo' ? (
                <label className="item-marcar" title="Selecionar para criar um bloco">
                  <input
                    type="checkbox"
                    checked={selecionados.has(i)}
                    onChange={() => setSelecionados((s) => alternar(s, i))}
                    aria-label={`Selecionar o passo ${i + 1}`}
                  />
                </label>
              ) : (
                <span className="item-marcar" />
              )}
              <span className="n">{i + 1}</span>

              <div className="item-corpo">
                {item.tipo === 'passo' && item.passo ? (
                  <Passo
                    passo={item.passo}
                    editando={editando?.indice === i ? editando.valor : null}
                    onMudarEdicao={(valor) => setEditando({ indice: i, valor })}
                    onConfirmar={confirmarEdicao}
                    onCancelar={() => setEditando(null)}
                  />
                ) : (
                  <Bloco
                    item={item}
                    aberto={expandidos.has(i)}
                    onAlternar={() => setExpandidos((s) => alternar(s, i))}
                  />
                )}
              </div>

              <div className="item-acoes">
                {item.passo?.editavel && (
                  <button type="button" className="icone-btn mini" title="Editar o valor"
                    aria-label={`Editar o valor do passo ${i + 1}`}
                    onClick={() => setEditando({ indice: i, valor: item.passo?.value ?? '' })}>
                    <Icone nome="lapis" tamanho={13} />
                  </button>
                )}
                <button type="button" className="icone-btn mini" disabled={i === 0} title="Subir"
                  aria-label={`Subir o item ${i + 1}`} onClick={() => mover(i, i - 1)}>
                  <Icone nome="cima" tamanho={13} />
                </button>
                <button type="button" className="icone-btn mini" disabled={i === itens.length - 1} title="Descer"
                  aria-label={`Descer o item ${i + 1}`} onClick={() => mover(i, i + 1)}>
                  <Icone nome="baixo" tamanho={13} />
                </button>
                <button type="button" className="icone-btn mini perigo" title="Remover"
                  aria-label={`Remover o item ${i + 1}`} onClick={() => onRemover(i)}>
                  <Icone nome="x" tamanho={13} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="vazio">
          Nada gravado ainda. Cada ação que der certo — pelo chat ou pelo record — entra aqui,
          com o seletor usado.
        </p>
      )}

      {selecionados.size > 0 && (
        <form className="criar-bloco" onSubmit={criarBloco}>
          <p>
            <Icone nome="bloco" tamanho={13} />
            <strong>{selecionados.size} passo(s)</strong> viram um bloco reutilizável
          </p>
          <div className="linha-form">
            <input
              value={nomeBloco}
              onChange={(e) => setNomeBloco(e.target.value)}
              placeholder="Nome do bloco, ex.: Login"
              aria-label="Nome do bloco"
              autoFocus
            />
            <button type="submit" className="btn primario pequeno" disabled={!nomeBloco.trim()}>
              {blocoExistente ? 'Substituir' : 'Criar bloco'}
            </button>
            <button type="button" className="icone-btn" onClick={() => setSelecionados(new Set())}
              aria-label="Cancelar a seleção" title="Cancelar">
              <Icone nome="x" tamanho={14} />
            </button>
          </div>
          {blocoExistente && (
            <p className="aviso-campo">
              Já existe o bloco “{blocoExistente.nome}”.
              {blocoExistente.usado_em.length
                ? ` Os testes que o usam (${blocoExistente.usado_em.join(', ')}) passam a rodar esta versão.`
                : ' Ele será substituído.'}
            </p>
          )}
        </form>
      )}

      <form className="salvar" onSubmit={salvarTeste}>
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do teste"
          aria-label="Nome do teste"
          disabled={!itens.length}
        />
        <button type="submit" className="btn primario pequeno" disabled={!itens.length || !nome.trim() || salvando}>
          <Icone nome="salvar" tamanho={14} />
          {testeExistente ? 'Sobrescrever' : 'Salvar teste'}
        </button>
      </form>
      {testeExistente && (
        <p className="aviso-campo">Já existe um teste com esse nome — salvar vai substituí-lo.</p>
      )}
    </section>
  );
}

function Passo({ passo, editando, onMudarEdicao, onConfirmar, onCancelar }: {
  passo: PassoView;
  editando: string | null;
  onMudarEdicao: (valor: string) => void;
  onConfirmar: (e: FormEvent) => void;
  onCancelar: () => void;
}) {
  const alvo = alvoDoRotulo(passo.label);
  return (
    <>
      <div className="item-linha">
        <span className={'acao acao-' + passo.action}>{nomeDaAcao(passo.action)}</span>
        <span className="item-rotulo" title={passo.label}>{alvo || passo.label}</span>
      </div>
      {editando !== null ? (
        <form className="editar-valor" onSubmit={onConfirmar}>
          <input
            value={editando}
            onChange={(e) => onMudarEdicao(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && onCancelar()}
            aria-label="Novo valor"
            autoFocus
          />
          <button type="submit" className="icone-btn mini" aria-label="Confirmar"><Icone nome="check" tamanho={13} /></button>
          {passo.action === 'expect_text' && (
            <small>Dado que muda a cada execução? Troque por máscara: XXXX-X, ###.</small>
          )}
        </form>
      ) : (
        VALOR_A_PARTE.has(passo.action) && (
          <div className="item-valor" title={passo.value}>{passo.value || '(vazio)'}</div>
        )
      )}
      {passo.selector_code && <code title={passo.selector_code}>{passo.selector_code}</code>}
    </>
  );
}

function Bloco({ item, aberto, onAlternar }: { item: ItemView; aberto: boolean; onAlternar: () => void }) {
  return (
    <>
      <button type="button" className="item-linha bloco-abrir" onClick={onAlternar} aria-expanded={aberto}>
        <span className="acao acao-bloco"><Icone nome="bloco" tamanho={11} /> bloco</span>
        <span className="item-rotulo">{item.bloco_nome}</span>
        {!item.bloco_ausente && <span className="bloco-qtd">{item.bloco_passos.length} passo(s)</span>}
        <span className={'chevron' + (aberto ? ' aberto' : '')}><Icone nome="baixo" tamanho={13} /></span>
      </button>
      {item.bloco_ausente && <p className="item-erro">Esse bloco foi excluído — o teste vai falhar aqui.</p>}
      {aberto && <ListaDePassos passos={item.bloco_passos} />}
    </>
  );
}

export function ListaDePassos({ passos }: { passos: PassoView[] }) {
  return (
    <ol className="bloco-passos">
      {passos.map((p, j) => (
        <li key={j}>
          <span className={'acao acao-' + p.action}>{nomeDaAcao(p.action)}</span>
          <span title={p.selector_code || p.label}>
            {alvoDoRotulo(p.label) || p.label}
            {VALOR_A_PARTE.has(p.action) && p.value ? <em> = {p.value}</em> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
