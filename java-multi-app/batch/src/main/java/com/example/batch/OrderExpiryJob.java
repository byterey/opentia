package com.example.batch;

import com.example.core.model.Order;
import com.example.infrastructure.InMemoryOrderRepository;
import java.util.List;

public class OrderExpiryJob {
    private final InMemoryOrderRepository repository;

    public OrderExpiryJob(InMemoryOrderRepository repository) {
        this.repository = repository;
    }

    public int run() {
        List<Order> all = repository.findAll();
        int expired = 0;
        for (Order order : all) {
            if ("PENDING".equals(order.getStatus())) {
                order.setStatus("EXPIRED");
                repository.save(order);
                expired++;
            }
        }
        return expired;
    }
}
