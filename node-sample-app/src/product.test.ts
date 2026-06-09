import { formatProductLabel, Product } from './product';

describe('formatProductLabel', () => {
  it('formats with two decimal places', () => {
    const p: Product = { id: '1', name: 'Widget', price: 9.9 };
    expect(formatProductLabel(p)).toBe('Widget — $9.90');
  });

  it('includes product name', () => {
    const p: Product = { id: '2', name: 'Gadget', price: 100 };
    expect(formatProductLabel(p)).toContain('Gadget');
  });
});
