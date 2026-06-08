package com.example.services;

import com.example.core.model.Order;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class OrderService {
    private final List<Order> orders = new ArrayList<>();

    public void place(Order order) {
        orders.add(order);
    }

    public Optional<Order> findById(String id) {
        return orders.stream().filter(o -> o.getId().equals(id)).findFirst();
    }

    public List<Order> findAll() {
        return List.copyOf(orders);
    }

    public boolean cancel(String id) {
        return findById(id).map(o -> {
            o.setStatus("CANCELLED");
            return true;
        }).orElse(false);
    }
}
