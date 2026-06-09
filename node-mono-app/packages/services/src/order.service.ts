import { Order } from '@example/core';

export class OrderService {
  private orders: Order[] = [];

  create(total: number): Order {
    const order: Order = { id: String(Date.now()), total, status: 'pending' };
    this.orders.push(order);
    return order;
  }

  confirm(id: string): void {
    const order = this.orders.find(o => o.id === id);
    if (order) order.status = 'confirmed';
  }

  list(): Order[] {
    return [...this.orders];
  }
}
