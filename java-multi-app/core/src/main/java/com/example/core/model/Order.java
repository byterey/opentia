package com.example.core.model;

public class Order {
    private final String id;
    private String status;
    private double total;

    public Order(String id, double total) {
        this.id = id;
        this.status = "PENDING";
        this.total = total;
    }

    public String getId() { return id; }
    public String getStatus() { return status; }
    public double getTotal() { return total; }
    public void setStatus(String status) { this.status = status; }

    public boolean isExpired() {
        return "EXPIRED".equals(status);
    }
}

