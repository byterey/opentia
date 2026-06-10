package com.example.app

import com.example.core.model.Money

class MainViewModel {

    fun load(): String = "ok"

    fun balance(): Money = Money(0)

    private fun helper(): Int = 1
}
