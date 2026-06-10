package com.appa.services;

import com.appa.core.Order;

public class OrderService {

    public double totalWithTax(Order order, double rate) {
        return order.getTotal() * (1.0 + rate);
    }
}
