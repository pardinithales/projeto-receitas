// Calcula unidades/dia a partir do texto da posologia (pt-BR do consultório).
// Entende: "Tomar 3 comprimidos à noite", "2 cápsulas de 8 em 8 horas",
// "1 cp 12/12h", "5 x ao dia", esquemas "3-0-3" / "1-1-1", "1 + ½".
// Retorna null quando não dá para inferir com segurança (aí não mexe no campo).
function unidadesPorDia(texto) {
  const t = (texto || '').toLowerCase().replace(',', '.');
  if (!t.trim()) return null;
  if (t.includes('ml') || t.includes('gota') || t.includes('aplicar')) return null;

  // esquema tipo 3-0-3, 1-1-1, 2-0-2 (soma das tomadas)
  const esquema = t.match(/(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)/);
  if (esquema) return (+esquema[1]) + (+esquema[2]) + (+esquema[3]);

  // dose por tomada: "3 comprimidos", "1 cp", "2 cápsulas", "1 + ½"
  let dose = 1;
  const meio = t.match(/(\d+)\s*\+\s*(?:½|1\/2|meio)/);
  const d = t.match(/(?:tomar\s+)?(\d+(?:\.\d+)?)\s*(?:comprimidos?|c[aá]psulas?|cps?|cp\b)/);
  if (meio) dose = (+meio[1]) + 0.5;
  else if (d) dose = +d[1];

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

// qtd mensal (30 dias) inteira, ou null
function qtdMensalDaPosologia(texto) {
  const dia = unidadesPorDia(texto);
  return dia == null ? null : Math.ceil(dia * 30);
}
