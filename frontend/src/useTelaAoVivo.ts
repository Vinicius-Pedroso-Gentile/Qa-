import { useEffect, useState } from 'react';

/**
 * Transmissao da tela do browser: devolve a URL do quadro mais recente, ou null
 * quando nao ha pagina aberta (o servidor responde 204).
 *
 * O servidor guarda o ultimo quadro do screencast do Chromium, entao pedir e barato;
 * a tela diz qual quadro ja tem (?n=) e, se nada mudou, a resposta e um 304 vazio.
 * Por isso da para pedir a cada 100ms: antes era um screenshot novo a cada 350ms, e
 * o que se digitava aparecia com quase meio segundo de atraso.
 *
 * Pede um quadro novo so depois que o anterior chegou, para nunca empilhar
 * requisicoes. Com a aba escondida, nao pede nada.
 */
export function useTelaAoVivo(intervaloMs = 80): string | null {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    let timer: number | undefined;
    let atual: string | null = null;
    let numero = -2;

    function trocar(novo: string | null) {
      // Cada quadro e um blob novo; sem revogar o anterior, a memoria cresce a cada quadro.
      if (atual) URL.revokeObjectURL(atual);
      atual = novo;
      setSrc(novo);
    }

    async function quadro() {
      if (!document.hidden) {
        try {
          const resposta = await fetch(`/api/tela?n=${numero}`, { cache: 'no-store' });
          if (!ativo) return;
          if (resposta.status === 204) {
            numero = -2;
            trocar(null);
          } else if (resposta.status === 200) {
            const blob = await resposta.blob();
            if (!ativo) return;
            numero = Number(resposta.headers.get('X-Quadro') ?? -2);
            trocar(URL.createObjectURL(blob));
          }
          // 304: o quadro que ja esta na tela continua sendo o atual.
        } catch {
          // servidor caiu ou reiniciou: mantem o ultimo quadro e tenta de novo
        }
      }
      if (ativo) timer = window.setTimeout(quadro, intervaloMs);
    }

    quadro();
    return () => {
      ativo = false;
      window.clearTimeout(timer);
      if (atual) URL.revokeObjectURL(atual);
    };
  }, [intervaloMs]);

  return src;
}
