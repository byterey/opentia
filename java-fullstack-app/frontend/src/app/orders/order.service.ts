import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Order {
  id: string;
  status: string;
  total: number;
}

@Injectable({ providedIn: 'root' })
export class OrderService {
  private readonly apiUrl = '/api/orders';

  constructor(private http: HttpClient) {}

  list(): Observable<Order[]> {
    return this.http.get<Order[]>(this.apiUrl);
  }

  create(total: number): Observable<Order> {
    return this.http.post<Order>(this.apiUrl, { total });
  }

  confirm(id: string): Observable<void> {
    return this.http.post<void>(`${this.apiUrl}/${id}/confirm`, {});
  }
}
