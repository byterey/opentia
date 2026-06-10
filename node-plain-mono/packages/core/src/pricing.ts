export function computePrice(qty: number, unit: number): number {
  return qty * unit;
}

export function applyDiscount(total: number, percent: number): number {
  return total * (1 - percent / 100);
}
