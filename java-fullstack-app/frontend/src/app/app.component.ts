import { Component } from '@angular/core';
import { OrderListComponent } from './order-list/order-list.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [OrderListComponent],
  template: `<app-order-list />`,
})
export class AppComponent {}
