package com.appa.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class OrderTest {

    @Test
    void getId_returnsId() {
        Order order = new Order("o-1", 10.0);
        assertEquals("o-1", order.getId());
    }

    @Test
    void getTotal_returnsTotal() {
        Order order = new Order("o-2", 25.5);
        assertEquals(25.5, order.getTotal());
    }
}
