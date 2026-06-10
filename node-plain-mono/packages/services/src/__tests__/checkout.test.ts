import { checkoutTotal } from '../checkout';

test('checkoutTotal returns line amount', () => {
  expect(checkoutTotal(3, 4)).toBe(12);
});
