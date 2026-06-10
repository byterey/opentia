import { computePrice, applyDiscount } from '../pricing';

test('computePrice multiplies quantity by unit', () => {
  expect(computePrice(2, 5)).toBe(10);
});

test('applyDiscount reduces total', () => {
  expect(applyDiscount(100, 10)).toBe(90);
});
