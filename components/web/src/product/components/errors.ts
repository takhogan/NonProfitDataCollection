import { ProductApiError } from '../../api/product';
import { translateP, type ProductKey } from '../i18n';
import type { Lang } from '../../locales/i18n';

/** Map an API error to a product i18n message. */
export function errorText(err: unknown, lang: Lang): string {
  if (err instanceof ProductApiError) {
    const key = `error.${err.code}` as ProductKey;
    const mapped = translateP(lang, key);
    // translateP returns the key itself when unknown; fall back to the server message.
    if (mapped !== key) return mapped;
    if (err.status === 0) return translateP(lang, 'error.network');
    return err.message || translateP(lang, 'error.generic');
  }
  return translateP(lang, 'error.generic');
}
