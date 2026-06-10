package com.example.core.model

class Discount(val percent: Int) {

    fun apply(money: Money): Money =
        Money(money.amount * (100 - percent) / 100)
}
