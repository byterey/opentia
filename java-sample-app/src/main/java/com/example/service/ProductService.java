package com.example.service;

import com.example.model.Product;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class ProductService {
    private final List<Product> products = new ArrayList<>();

    public void addProduct(Product product) {
        products.add(product);
    }

    public Optional<Product> findById(String id) {
        return products.stream().filter(p -> p.getId().equals(id)).findFirst();
    }

    public List<Product> findAll() {
        return List.copyOf(products);
    }

    public boolean applyDiscount(String id, double percent) {
        return findById(id).map(p -> {
            p.setPrice(p.getPrice() * (1 - percent / 100));
            return true;
        }).orElse(false);
    }
}

