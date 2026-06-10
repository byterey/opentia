package com.appb.services;

import com.appb.core.Gadget;

public class GadgetService {

    public Gadget provision() {
        Gadget gadget = new Gadget();
        gadget.activate();
        return gadget;
    }
}
