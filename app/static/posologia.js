// Calcula unidades/dia a partir do texto da posologia (pt-BR do consultório).
// Entende: "Tomar 3 comprimidos à noite", "2 cápsulas de 8 em 8 horas",
// "1 cp 12/12h", "5 x ao dia", esquemas "3-0-3" / "1-1-1" / "½-0-½",
// frações ("meio comprimido", "½", "1/2", "0,5", "¼", "1 + ½").
// Titulação em várias linhas ("Do dia 1 ao 14: … ⏎ A partir do dia 15: …"):
// vale a ÚLTIMA linha calculável (dose de manutenção, a maior).
// Retorna null quando não dá para inferir com segurança (aí não mexe no campo).

const FRACAO = '(?:½|¼|¾|meio|meia|\\d+\\s*/\\s*\\d+|\\d+(?:[.,]\\d+)?)';

function valorFracao(s) {
  s = (s || '').replace(/\s+/g, '');
  if (s === '½' || s === 'meio' || s === 'meia') return 0.5;
  if (s === '¼') return 0.25;
  if (s === '¾') return 0.75;
  const fr = s.match(/^(\d+)\/(\d+)$/);
  if (fr && +fr[2] !== 0) return +fr[1] / +fr[2];
  const n = parseFloat(s.replace(',', '.'));
  return isNaN(n) ? 0 : n;
}

function unidadesPorDiaLinha(t) {
  if (!t.trim()) return null;

  // esquema tipo 3-0-3, 1-1-1, ½-0-½ (soma das tomadas)
  const esquema = t.match(new RegExp(`(${FRACAO})\\s*-\\s*(${FRACAO})\\s*-\\s*(${FRACAO})`));
  if (esquema)
    return valorFracao(esquema[1]) + valorFracao(esquema[2]) + valorFracao(esquema[3]);

  // dose por tomada: "3 comprimidos", "1 cp", "meio comprimido", "1 + ½ cp", "0,5 cps"
  let dose = 1;
  const d = t.match(new RegExp(
    `(?:tomar\\s+)?(${FRACAO})(?:\\s*\\+\\s*(${FRACAO}))?\\s*(?:de\\s+)?(?:comprimidos?|c[aá]psulas?|cps?|cp\\b)`));
  if (d) dose = valorFracao(d[1]) + (d[2] ? valorFracao(d[2]) : 0);

  // frequência
  const cada = t.match(/(\d+)\s*(?:em|\/)\s*\1\s*h/) || t.match(/de\s*(\d+)\s*em\s*\d+\s*horas?/);
  if (cada) {
    const h = +cada[1];
    if (h >= 4 && h <= 24) return dose * (24 / h);
  }
  const vezes = t.match(/(\d+)\s*(?:x|vezes)\s*(?:ao|por)\s*dia/);
  if (vezes) return dose * (+vezes[1]);
  if (/(por dia|ao dia|1x|uma vez|noite|manh[ãa]|jantar|almo[çc]o|deitar|dormir)/.test(t))
    return dose;
  return null;
}

function unidadesPorDia(texto) {
  const t = (texto || '').toLowerCase();
  if (!t.trim()) return null;
  if (t.includes('ml') || t.includes('gota') || t.includes('aplicar')) return null;
  let ultimo = null;
  for (const linha of t.split('\n')) {
    const v = unidadesPorDiaLinha(linha);
    if (v != null) ultimo = v;   // titulação: vale a última linha calculável
  }
  return ultimo;
}

// qtd mensal (30 dias) inteira, ou null
function qtdMensalDaPosologia(texto) {
  const dia = unidadesPorDia(texto);
  return dia == null ? null : Math.ceil(dia * 30);
}

// unidade que acompanha a quantidade, deduzida do texto da apresentação
// ("50mg - comprimido" -> "comprimidos", "5000mcg - ampola IM" -> "ampolas")
function unidadeDaForma(texto) {
  const t = (texto || '').toLowerCase();
  if (t.includes('cápsula') || t.includes('capsula')) return 'cápsulas';
  if (t.includes('comprimido')) return 'comprimidos';
  if (t.includes('ampola')) return 'ampolas';
  if (t.includes('frasco')) return 'frascos';
  if (t.includes('adesivo')) return 'adesivos';
  if (t.includes('seringa')) return 'seringas';
  if (t.includes('sachê') || t.includes('sache')) return 'sachês';
  if (t.includes('supositório') || t.includes('supositorio')) return 'supositórios';
  return 'unidades';
}
