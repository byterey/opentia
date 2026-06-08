package com.example.service;

import com.example.model.Product;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class ProductServiceTest {
    private ProductService productService;

    @BeforeEach
    void setUp() {
        productService = new ProductService();
        productService.addProduct(new Product("p1", "Widget", 10.0));
        productService.addProduct(new Product("p2", "Gadget", 25.0));
    }

    @Test
    void findById_returnsProduct() {
        assertTrue(productService.findById("p1").isPresent());
    }

    @Test
    void findAll_returnsAllProducts() {
        assertEquals(2, productService.findAll().size());
    }

    @Test
    void applyDiscount_reducesPrice() {
        productService.applyDiscount("p1", 10);
        assertEquals(9.0, productService.findById("p1").get().getPrice(), 0.001);
    }

    @Test
    void applyDiscount_missingId_returnsFalse() {
        assertFalse(productService.applyDiscount("nonexistent", 10));
    }
}
