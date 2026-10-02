// Icones em SVG inline: nenhuma dependencia a mais so para desenhar meia duzia de tracos.

const TRACOS = {
  chat: 'M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z',
  record: 'M12 12m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0',
  play: 'M7 5l12 7-12 7z',
  x: 'M6 6l12 12M18 6L6 18',
  copiar: 'M9 9h10v10H9zM5 15V5h10',
  check: 'M5 12.5l4.5 4.5L19 7',
  enviar: 'M4 12l16-8-6 16-2.5-6.5z',
  power: 'M12 3v8M6.3 6.3a8 8 0 1 0 11.4 0',
  seta: 'M9 6l6 6-6 6',
  globo: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18',
  lixo: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  salvar: 'M5 4h11l3 3v13H5zM8 4v5h7M8 20v-6h8v6',
  bloco: 'M4 5h16v5H4zM4 14h16v5H4z',
  cima: 'M6 15l6-6 6 6',
  baixo: 'M6 9l6 6 6-6',
  lapis: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  mais: 'M12 5v14M5 12h14',
  cursor: 'M5 3l14 7-6 2-2 6z',
  texto: 'M5 6V4h14v2M12 4v16M9 20h6',
  parar: 'M7 7h10v10H7z',
  teclado: 'M3 6h18v12H3zM7 10h.01M11 10h.01M15 10h.01M7 14h10',
} as const;

export type NomeIcone = keyof typeof TRACOS;

export function Icone({ nome, tamanho = 16 }: { nome: NomeIcone; tamanho?: number }) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill={nome === 'play' || nome === 'record' || nome === 'parar' ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={TRACOS[nome]} />
    </svg>
  );
}
