package com.appb.services;

import com.appb.core.Gadget;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class GadgetServiceTest {

    @Test
    void provision_returnsActiveGadget() {
        Gadget gadget = new GadgetService().provision();
        assertTrue(gadget.isActive());
    }
}
