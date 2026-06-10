package com.example.core.model

import org.junit.Assert.assertEquals
import org.junit.Test

class MoneyTest {

    @Test
    fun plus_addsAmounts() {
        assertEquals(Money(30), Money(10).plus(Money(20)))
    }

    @Test
    fun discount_reducesAmount() {
        assertEquals(Money(90), Discount(10).apply(Money(100)))
    }
}
