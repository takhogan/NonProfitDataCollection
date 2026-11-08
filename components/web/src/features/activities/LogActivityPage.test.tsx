import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MockApiClient } from '../../api';
import { FIXED_NOW, renderApp } from '../../test/renderApp';

describe('Log activity (WEB-014, WEB-005)', () => {
  it('validates required areas and days before saving', async () => {
    const user = userEvent.setup();
    renderApp('/activities/new');
    await user.click(await screen.findByRole('button', { name: 'Guardar actividad' }));
    expect(await screen.findAllByText('Elige al menos un área.')).not.toHaveLength(0);
    expect(screen.getByText('Elige al menos un día.')).toBeInTheDocument();
  });

  it('keeps input after a failed save and retries with the same operation key', async () => {
    const user = userEvent.setup();
    const client = new MockApiClient({ now: FIXED_NOW, latencyMs: 0 });
    const spy = vi.spyOn(client, 'createActivity');
    client.failNextWrite('network_error');
    const { router } = renderApp('/activities/new?area=sec-esperanza&category=water_drinking', { client });

    await user.click(await screen.findByRole('checkbox', { name: 'lun' }));
    await user.type(screen.getByLabelText(/Capacidad/), '1500');
    await user.click(screen.getByRole('button', { name: 'Guardar actividad' }));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('No se guardó.')).toBeInTheDocument();
    // No optimistic success; input preserved.
    expect(router.state.location.pathname).toBe('/activities/new');
    expect(screen.getByLabelText(/Capacidad/)).toHaveValue(1500);
    expect(screen.getByRole('checkbox', { name: /La Esperanza/ })).toBeChecked();

    await user.click(within(alert).getByRole('button', { name: 'Reintentar guardado' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/activities'));
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[0]![0].operation_key).toBe(spy.mock.calls[1]![0].operation_key);
    expect(await screen.findByText(/Actividad guardada/)).toBeInTheDocument();

    // Shows on the coverage view right away.
    const cov = await client.getCoverage({ bucket: '24h', category: 'water_drinking' });
    expect(cov.items.find((c) => c.area.id === 'sec-esperanza')!.status).toBe('covered');
  });
});
