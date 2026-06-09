import { isPending, Order } from '../order';

describe('isPending', () => {
  it('returns true for pending order', () => {
    const o: Order = { id: '1', total: 50, status: 'pending' };
    expect(isPending(o)).toBe(true);
  });

  it('returns false for confirmed order', () => {
    const o: Order = { id: '2', total: 50, status: 'confirmed' };
    expect(isPending(o)).toBe(false);
  });
});
