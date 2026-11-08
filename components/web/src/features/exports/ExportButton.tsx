import { useI18n } from '../../locales/i18n';

/** Builds the file in memory and hands it to the browser; nothing is stored. */
export function ExportButton({ filename, build }: { filename: string; build: () => string }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className="secondary"
      onClick={() => {
        const blob = new Blob(['﻿', build()], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}.csv`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 0);
      }}
    >
      {t('export.csv')}
    </button>
  );
}
