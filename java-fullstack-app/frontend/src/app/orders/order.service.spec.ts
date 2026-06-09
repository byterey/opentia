import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { OrderService } from './order.service';

describe('OrderService', () => {
  let service: OrderService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [OrderService],
    });
    service = TestBed.inject(OrderService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('list() calls GET /api/orders', () => {
    service.list().subscribe();
    http.expectOne('/api/orders').flush([]);
  });

  it('create() calls POST /api/orders', () => {
    service.create(99).subscribe();
    http.expectOne('/api/orders').flush({ id: '1', status: 'PENDING', total: 99 });
  });

  it('confirm() calls POST /api/orders/:id/confirm', () => {
    service.confirm('1').subscribe();
    http.expectOne('/api/orders/1/confirm').flush(null);
  });
});
