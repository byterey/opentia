import { Product } from './product';

export class ProductService {
  private products: Product[] = [];

  add(product: Product): void {
    this.products.push(product);
  }

  findById(id: string): Product | undefined {
    return this.products.find(p => p.id === id);
  }

  list(): Product[] {
    return [...this.products];
  }
}
