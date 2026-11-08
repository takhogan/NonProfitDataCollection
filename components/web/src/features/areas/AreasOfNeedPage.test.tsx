import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';

describe('Areas of need (WEB-010, WEB-004)', () => {
  it('shows the ranking criteria, ranked rows with units, and unranked areas labelled honestly', async () => {
    renderApp('/areas');
    expect(await screen.findByRole('heading', { name: 'Cómo se ordena esta lista' })).toBeInTheDocument();
    expect(screen.getByText('Necesidades urgentes activas')).toBeInTheDocument();
    expect(screen.getByText(/Método rank-v1/)).toBeInTheDocument();

    const table = screen.getByRole('table');
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows.length).toBeGreaterThan(5);
    expect(within(rows[0]!).getByText('#1')).toBeInTheDocument();
    expect(within(rows[0]!).getAllByText(/necesidades activas/).length).toBeGreaterThan(0);
    expect(within(rows[0]!).getByText(/Actualizado/)).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/Confianza/)).toBeInTheDocument();

    const unranked = screen.getByRole('heading', { name: 'Áreas sin clasificar' }).parentElement!;
    expect(within(unranked).getAllByText('Datos insuficientes').length).toBeGreaterThan(0);
    expect(within(unranked).getAllByText('Sin datos').length).toBeGreaterThan(0);
  });

  it('opens confidence reasons on tap or keyboard, not only on hover', async () => {
    const user = userEvent.setup();
    renderApp('/areas');
    const table = await screen.findByRole('table');
    const firstBadge = within(table).getAllByText(/Confianza (alta|media|baja)/)[0]!;
    await user.click(firstBadge);
    const reasons = within(table).getAllByRole('list', { name: 'Motivos de la confianza' })[0]!;
    expect(reasons).toBeVisible();
    expect(within(reasons).getAllByRole('listitem').length).toBeGreaterThan(0);
  });

  it('can switch to English', async () => {
    const user = userEvent.setup();
    renderApp('/areas');
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: 'English' }));
    expect(await screen.findByRole('heading', { name: 'Areas of need' })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');
  });
});
