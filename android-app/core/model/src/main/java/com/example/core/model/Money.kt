package com.example.core.model

data class Money(val amount: Long) {

    fun plus(other: Money): Money = Money(amount + other.amount)
}
