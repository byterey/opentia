package com.example.backend.controller;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderControllerTest {
    private OrderController controller;

    @BeforeEach
    void setUp() {
        controller = new OrderController();
    }

    @Test
    void create_addsOrder() {
        controller.create("o1", 99.0);
        assertEquals(1, controller.list().size());
    }

    @Test
    void confirm_setsStatusConfirmed() {
        controller.create("o1", 99.0);
        assertTrue(controller.confirm("o1"));
        assertEquals("CONFIRMED", controller.list().get(0).getStatus());
    }

    @Test
    void confirm_unknownId_returnsFalse() {
        assertFalse(controller.confirm("nonexistent"));
    }
}
