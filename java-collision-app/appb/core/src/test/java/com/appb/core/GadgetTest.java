package com.appb.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class GadgetTest {

    @Test
    void activate_setsActive() {
        Gadget gadget = new Gadget();
        gadget.activate();
        assertTrue(gadget.isActive());
    }
}
