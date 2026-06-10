package com.appa.services;

import com.appa.core.Order;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class OrderServiceTest {

    @Test
    void totalWithTax_appliesRate() {
        OrderService service = new OrderService();
        Order order = new Order("o-1", 100.0);
        assertEquals(110.0, service.totalWithTax(order, 0.10));
    }
}
