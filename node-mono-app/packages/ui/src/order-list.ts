import { OrderService } from '@example/services';

export class OrderListViewModel {
  constructor(private service: OrderService) {}

  getLabels(): string[] {
    return this.service.list().map(o => `#${o.id} ${o.status} $${o.total}`);
  }
}
