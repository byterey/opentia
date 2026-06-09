package com.example.backend.controller;

import com.example.domain.model.Order;
import java.util.ArrayList;
import java.util.List;

public class OrderController {
    private final List<Order> orders = new ArrayList<>();

    public Order create(String id, double total) {
        Order order = new Order(id, total);
        orders.add(order);
        return order;
    }

    public List<Order> list() {
        return List.copyOf(orders);
    }

    public boolean confirm(String id) {
        return orders.stream()
            .filter(o -> o.getId().equals(id))
            .findFirst()
            .map(o -> { o.setStatus("CONFIRMED"); return true; })
            .orElse(false);
    }
}
