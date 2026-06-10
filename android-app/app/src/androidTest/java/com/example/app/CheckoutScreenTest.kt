package com.example.app

import org.junit.Assert.assertEquals
import org.junit.Test

class CheckoutScreenTest {

    @Test
    fun render_showsCheckout() {
        assertEquals("checkout", CheckoutScreen().render())
    }
}
