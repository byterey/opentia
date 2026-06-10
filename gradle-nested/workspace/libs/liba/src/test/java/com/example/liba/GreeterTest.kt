package com.example.liba

import org.junit.Assert.assertEquals
import org.junit.Test

class GreeterTest {

    @Test
    fun greet_includesName() {
        assertEquals("hello, kim", Greeter().greet("kim"))
    }
}
