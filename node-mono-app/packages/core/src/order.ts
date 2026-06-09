export interface Order {
  id: string;
  total: number;
  status: 'pending' | 'confirmed' | 'cancelled';
}

export function isPending(order: Order): boolean {
  return order.status === 'pending';
}
