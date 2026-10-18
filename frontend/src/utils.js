export const pct=v=>v===null || v===undefined ? '—' : `${v}%`;
export const initials=n=>n.split(' ').slice(0,2).map(w=>w[0]).join('');
