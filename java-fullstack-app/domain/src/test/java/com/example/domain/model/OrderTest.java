package com.example.domain.model;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderTest {

    @Test
    void newOrder_isPending() {
        Order order = new Order("1", 50.0);
        assertTrue(order.isPending());
        assertEquals("PENDING", order.getStatus());
    }

    @Test
    void setStatus_updatesStatus() {
        Order order = new Order("2", 100.0);
        order.setStatus("CONFIRMED");
        assertFalse(order.isPending());
        assertEquals("CONFIRMED", order.getStatus());
    }
}
