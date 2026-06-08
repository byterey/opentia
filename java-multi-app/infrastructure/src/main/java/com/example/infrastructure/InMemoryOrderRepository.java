package com.example.infrastructure;

import com.example.core.model.Order;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class InMemoryOrderRepository {
    private final List<Order> store = new ArrayList<>();

    public void save(Order order) {
        store.removeIf(o -> o.getId().equals(order.getId()));
        store.add(order);
    }

    public Optional<Order> findById(String id) {
        return store.stream().filter(o -> o.getId().equals(id)).findFirst();
    }

    public List<Order> findAll() {
        return List.copyOf(store);
    }

    public void delete(String id) {
        store.removeIf(o -> o.getId().equals(id));
    }
}
