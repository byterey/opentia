package com.example.feature.checkout

import com.example.core.model.Money
import org.junit.Assert.assertEquals
import org.junit.Test

class CheckoutEngineTest {

    @Test
    fun total_sumsLines() {
        val engine = CheckoutEngine()
        assertEquals(Money(30), engine.total(listOf(Money(10), Money(20))))
    }
}
