import { OrderListViewModel } from '../order-list';
import { OrderService } from '@example/services';

describe('OrderListViewModel', () => {
  it('returns empty labels when no orders', () => {
    const vm = new OrderListViewModel(new OrderService());
    expect(vm.getLabels()).toEqual([]);
  });

  it('formats order label correctly', () => {
    const service = new OrderService();
    const order = service.create(42);
    const vm = new OrderListViewModel(service);
    const labels = vm.getLabels();
    expect(labels[0]).toContain('pending');
    expect(labels[0]).toContain('42');
  });
});
