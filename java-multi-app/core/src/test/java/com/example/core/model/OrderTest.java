package com.example.core.model;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderTest {
    @Test
    void newOrder_isPending() {
        Order order = new Order("1", 100.0);
        assertEquals("PENDING", order.getStatus());
    }

    @Test
    void setStatus_expired_isExpired() {
        Order order = new Order("2", 50.0);
        order.setStatus("EXPIRED");
        assertTrue(order.isExpired());
    }
}
