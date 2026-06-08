package com.example.services;

import com.example.core.model.Order;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderServiceTest {
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService();
        orderService.place(new Order("o1", 99.0));
    }

    @Test
    void findById_returnsOrder() {
        assertTrue(orderService.findById("o1").isPresent());
    }

    @Test
    void cancel_setsStatusCancelled() {
        orderService.cancel("o1");
        assertEquals("CANCELLED", orderService.findById("o1").get().getStatus());
    }

    @Test
    void cancel_missingId_returnsFalse() {
        assertFalse(orderService.cancel("nonexistent"));
    }
}
