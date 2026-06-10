package com.example.libb

import org.junit.Assert.assertEquals
import org.junit.Test

class BannerTest {

    @Test
    fun render_showsWelcome() {
        assertEquals("*** welcome ***", Banner().render())
    }
}
