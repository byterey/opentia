package com.example.app

import org.jetbrains.annotations.TestOnly
import org.junit.Assert.assertEquals
import org.junit.Test

class MainViewModelTest {

    @Test
    fun load_returnsOk() {
        assertEquals("ok", MainViewModel().load())
    }

    private fun viewModelWithDefaults(): MainViewModel = MainViewModel()

    @TestOnly
    private fun seedViewModel(): MainViewModel = MainViewModel()
}
