import { Component, For } from 'solid-js';

interface ManaSymbolProps {
  cost?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const ManaSymbol: Component<ManaSymbolProps> = (props) => {
  if (!props.cost) return null;

  // Extraer símbolos entre llaves, ej. "{2}{U}{U}" -> ["2", "U", "U"]
  const symbols = () => {
    const raw = props.cost || '';
    const matches = raw.match(/\{([^}]+)\}/g);
    if (!matches) return [];
    return matches.map((m) => m.replace(/[{}]/g, ''));
  };

  const getSymbolClass = (sym: string) => {
    const s = sym.toUpperCase();
    if (['W', 'U', 'B', 'R', 'G', 'C'].includes(s)) {
      return `mana-${s}`;
    }
    if (s === 'T') return 'mana-tap';
    return 'mana-generic';
  };

  const getSymbolContent = (sym: string) => {
    const s = sym.toUpperCase();
    if (s === 'T') return '↷';
    return s;
  };

  const sizeClass = () => {
    if (props.size === 'sm') return 'w-[16px] h-[16px] text-[9px]';
    if (props.size === 'lg') return 'w-[24px] h-[24px] text-[13px]';
    return 'w-[20px] h-[20px] text-[11px]';
  };

  return (
    <span class="inline-flex items-center gap-1 flex-wrap align-middle">
      <For each={symbols()}>
        {(sym) => (
          <span
            class={`mana-circle ${getSymbolClass(sym)} ${sizeClass()}`}
            title={`Maná ${sym}`}
          >
            {getSymbolContent(sym)}
          </span>
        )}
      </For>
    </span>
  );
};
