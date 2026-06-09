export interface Product {
  id: string;
  name: string;
  price: number;
}

export function formatProductLabel(product: Product): string {
  return `${product.name} — $${product.price.toFixed(2)}`;
}
