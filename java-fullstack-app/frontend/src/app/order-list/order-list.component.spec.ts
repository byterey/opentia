import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { OrderListComponent } from './order-list.component';
import { OrderService } from '../orders/order.service';

describe('OrderListComponent', () => {
  let fixture: ComponentFixture<OrderListComponent>;
  let mockService: jasmine.SpyObj<OrderService>;

  beforeEach(async () => {
    mockService = jasmine.createSpyObj('OrderService', ['list']);
    mockService.list.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [OrderListComponent],
      providers: [{ provide: OrderService, useValue: mockService }],
    }).compileComponents();

    fixture = TestBed.createComponent(OrderListComponent);
    fixture.detectChanges();
  });

  it('creates the component', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('loads orders on init', () => {
    expect(mockService.list).toHaveBeenCalled();
  });
});
