// Мини-эмулятор `sdk/db`: DSL схемы (только то, что использует проект) и тег sql``.
class Fragment {
  constructor(parts) { this.parts = parts; } // [{ text } | { value }]
  toQuery() {
    let text = ''; const params = [];
    for (const p of this.parts) {
      if ('text' in p) text += p.text;
      else { text += '?'; params.push(p.value === undefined ? null : p.value); }
    }
    return { text, params };
  }
}
export function sql(strings, ...values) {
  const parts = [];
  strings.forEach((s, i) => {
    parts.push({ text: s });
    if (i < values.length) {
      const v = values[i];
      if (v instanceof Fragment) parts.push(...v.parts);
      else if (typeof v === 'boolean') parts.push({ value: v ? 1 : 0 });
      else parts.push({ value: v });
    }
  });
  return new Fragment(parts);
}
sql.raw = (text) => new Fragment([{ text }]);
export { Fragment };

class Column {
  constructor(name, type) { this.name = name; this.type = type; this.mods = []; }
  primaryKey(o = {}) { this.mods.push(o.autoIncrement ? 'PRIMARY KEY AUTOINCREMENT' : 'PRIMARY KEY'); return this; }
  notNull() { this.mods.push('NOT NULL'); return this; }
  unique() { this.mods.push('UNIQUE'); return this; }
  default(v) { this.mods.push(`DEFAULT ${typeof v === 'string' ? `'${v}'` : v}`); return this; }
  ddl() { return [this.name, this.type, ...this.mods].join(' '); }
}
export const integer = (n) => new Column(n, 'INTEGER');
export const text = (n) => new Column(n, 'TEXT');
const idx = (unique) => (name) => ({ on: (...cols) => ({ name, unique, cols: cols.map((c) => c.name) }) });
export const index = idx(false);
export const uniqueIndex = idx(true);
export function table(name, columns, extras) {
  const t = { __table: name, columns: Object.values(columns), indexes: extras ? Object.values(extras(columns)) : [] };
  return t;
}
export function ddl(t) {
  return [
    `CREATE TABLE ${t.__table} (${t.columns.map((c) => c.ddl()).join(', ')})`,
    ...t.indexes.map((i) => `CREATE ${i.unique ? 'UNIQUE ' : ''}INDEX ${i.name} ON ${t.__table} (${i.cols.join(', ')})`),
  ];
}
