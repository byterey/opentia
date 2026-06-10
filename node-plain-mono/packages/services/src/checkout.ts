import { computePrice } from '@plain/core';

export function checkoutTotal(qty: number, unit: number): number {
  return computePrice(qty, unit);
}
