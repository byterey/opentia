import { ProductService } from './product.service';

describe('ProductService', () => {
  let service: ProductService;

  beforeEach(() => {
    service = new ProductService();
  });

  it('returns undefined for unknown id', () => {
    expect(service.findById('x')).toBeUndefined();
  });

  it('finds added product', () => {
    service.add({ id: '1', name: 'Widget', price: 10 });
    expect(service.findById('1')?.name).toBe('Widget');
  });

  it('lists all products', () => {
    service.add({ id: '1', name: 'A', price: 1 });
    service.add({ id: '2', name: 'B', price: 2 });
    expect(service.list()).toHaveLength(2);
  });
});
