import { OrderService } from '../order.service';

describe('OrderService', () => {
  let service: OrderService;

  beforeEach(() => {
    service = new OrderService();
  });

  it('creates order with pending status', () => {
    const order = service.create(100);
    expect(order.status).toBe('pending');
  });

  it('confirms an order', () => {
    const order = service.create(100);
    service.confirm(order.id);
    expect(service.list()[0].status).toBe('confirmed');
  });

  it('lists all orders', () => {
    service.create(10);
    service.create(20);
    expect(service.list()).toHaveLength(2);
  });
});
