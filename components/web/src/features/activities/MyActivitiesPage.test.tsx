import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';

describe('My activities (WEB-015)', () => {
  it('highlights activities unconfirmed for 7 days and confirms with one tap', async () => {
    const user = userEvent.setup();
    renderApp('/activities');
    const warning = await screen.findByText('Sin confirmar hace más de 7 días. ¿Sigue activa?');
    const card = warning.closest('li')!;
    await user.click(within(card).getByRole('button', { name: 'Sigue activa' }));
    await waitFor(() =>
      expect(screen.queryByText('Sin confirmar hace más de 7 días. ¿Sigue activa?')).not.toBeInTheDocument(),
    );
  });

  it('asks before ending an activity', async () => {
    const user = userEvent.setup();
    renderApp('/activities');
    const button = (await screen.findAllByRole('button', { name: 'Finalizar' }))[0]!;
    const card = button.closest('li')!;
    await user.click(within(card).getByRole('button', { name: 'Finalizar' }));
    await user.click(within(card).getByRole('button', { name: 'Sí, finalizar' }));
    await waitFor(() => expect(screen.getAllByText('Finalizada').length).toBeGreaterThan(0));
  });
});
