const MAP = {
  'sdk': './sdk/index.mjs',
  'sdk/db': './sdk/db.mjs',
  'sdk/api': './sdk/index.mjs',
  'sdk/fetch': './sdk/index.mjs',
};
export async function resolve(specifier, context, next) {
  if (specifier in MAP) return { url: new URL(MAP[specifier], import.meta.url).href, shortCircuit: true };
  return next(specifier, context);
}
