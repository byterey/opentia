package com.example.feature.checkout

import com.example.core.model.Money

class CheckoutEngine {

    fun total(lines: List<Money>): Money =
        lines.fold(Money(0)) { acc, line -> acc.plus(line) }
}
